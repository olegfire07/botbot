import logging
import json
import asyncio
import httpx
from pathlib import Path
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, InputMediaPhoto, InlineKeyboardMarkup, InlineKeyboardButton, CopyTextButton
from telegram.ext import CallbackContext, ConversationHandler, CommandHandler, MessageHandler, filters, CallbackQueryHandler
from modern_bot.config import (
    PROGRESS_STEPS, TOTAL_STEPS, MAX_PHOTOS, MAX_PHOTO_SIZE_MB, 
    PHOTO_REQUIREMENTS_MESSAGE, REGION_TOPICS, MAIN_GROUP_CHAT_ID, TEMP_PHOTOS_DIR
)
from modern_bot.utils.validators import is_digit, is_valid_ticket_number, normalize_region_input
from modern_bot.utils.files import generate_unique_filename, compress_image, is_image_too_large
from modern_bot.database.db import save_user_data, load_user_data, delete_user_data, check_ticket_duplicate, update_user_info
from modern_bot.services.docx_gen import create_document
from modern_bot.services.excel import update_excel
from modern_bot.services.archive import archive_document
from modern_bot.handlers.common import safe_reply, stream_safe_reply, send_document_from_path
from modern_bot.services.flow import finalize_conclusion
from modern_bot.services.photo import PhotoService

logger = logging.getLogger(__name__)

(DEPARTMENT, ISSUE_NUMBER, TICKET_NUMBER, DATE, REGION, PHOTO, DESCRIPTION, EVALUATION,
 MORE_PHOTO, CONFIRMATION, TESTING, WEB_APP_PHOTO, CONFIRM_DUPLICATE) = range(13)

def format_progress(stage: str) -> str:
    """Format the progress step string."""
    step = PROGRESS_STEPS.get(stage)
    return f"Шаг {step}/{TOTAL_STEPS}" if step else ""

async def start_conversation(update: Update, context: CallbackContext) -> int:
    """Start the conversation flow."""
    user = update.effective_user
    
    # GAMIFICATION: Update user info
    await update_user_info(user.id, user.username, user.first_name, user.last_name)
    
    await delete_user_data(user.id)
    await save_user_data(user.id, {'photo_desc': []})
    
    await safe_reply(
        update,
        f"👋 Привет! Начнем создание нового заключения.\n\n"
        f"🟡 {format_progress('department')}\nВведите номер подразделения:"
    )
    return DEPARTMENT

# In-memory guards to prevent concurrent duplicate processing of the same ticket number or user submission
PROCESSING_TICKETS = set()
PROCESSING_USERS = set()

async def process_submission_data(update: Update, context: CallbackContext, data: dict, user_id: int, user_name: str, award_points: bool = True) -> int:
    """Helper to process the valid data, download photos, and finalize."""
    ticket_num = str(data.get('ticket_number', '')).strip()
    user_id_str = str(user_id)

    # Guard against concurrent duplicate processing
    if ticket_num and ticket_num in PROCESSING_TICKETS:
        logger.warning(f"Ticket {ticket_num} is already being processed. Ignoring duplicate submission request.")
        return ConversationHandler.END

    if user_id_str in PROCESSING_USERS:
        logger.warning(f"User {user_id} is already generating a document. Ignoring duplicate submission request.")
        return ConversationHandler.END

    if ticket_num:
        PROCESSING_TICKETS.add(ticket_num)
    PROCESSING_USERS.add(user_id_str)

    try:
        # Prepare valid DB data structure
        db_data = {
            'department_number': str(data['department_number']),
            'issue_number': str(data['issue_number']),
            'ticket_number': str(data['ticket_number']),
            'date': data['date'],
            'region': data['region'],
            'photo_desc': []
        }

        user = update.effective_user
        if user:
            await update_user_info(
                user.id,
                user.username,
                user.first_name,
                user.last_name,
                last_region=data.get('region')
            )
        
        # Process items and download photos
        TEMP_PHOTOS_DIR.mkdir(parents=True, exist_ok=True)
        items = data.get('items', [])
        
        if len(items) > MAX_PHOTOS:
            logger.warning("Received %s items, trimming to MAX_PHOTOS=%s", len(items), MAX_PHOTOS)
            items = items[:MAX_PHOTOS]
            
        logger.info(f"Processing {len(items)} items for user {user_id}")

        async def download_item_photo(item, bot, client, sem):
            photo_url = item.get('photo_url')
            if not photo_url:
                return None
            async with sem:
                try:
                    return await PhotoService.download_photo(photo_url, bot, client)
                except Exception as e:
                    logger.error(f"Failed to download photo {photo_url}: {e}", exc_info=True)
                    return None

        semaphore = asyncio.Semaphore(5)
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            tasks = [
                download_item_photo(item, context.bot, client, semaphore)
                for item in items
            ]
            downloaded_paths = await asyncio.gather(*tasks)

        for idx, file_path in enumerate(downloaded_paths):
            if file_path:
                photo_entry = {
                    'photo': str(file_path),
                    'description': items[idx].get('description'),
                    'evaluation': items[idx].get('evaluation')
                }
                db_data['photo_desc'].append(photo_entry)
        
        await save_user_data(user_id, db_data)
        
        # Finalize
        is_test = data.get('is_test', False)
        
        await finalize_conclusion(
            context.bot, 
            user_id, 
            user_name, 
            db_data, 
            send_to_group=(not is_test), 
            award_points=(award_points and not is_test),
            msg_id=None
        )

        # Cleanup temp photos after successful generation
        try:
            for item in db_data.get('photo_desc', []):
                p_path = Path(item.get('photo', ''))
                if p_path.exists() and p_path.is_file():
                    if TEMP_PHOTOS_DIR in p_path.parents:
                        p_path.unlink()
        except Exception as e:
            logger.warning(f"Failed to cleanup temp photos: {e}")
        return ConversationHandler.END
        
    except Exception as e:
        logger.error(f"Error processing submission: {e}", exc_info=True)
        await safe_reply(update, "❌ Произошла ошибка при обработке данных.")
        return ConversationHandler.END
    finally:
        # Release concurrent processing guards
        if ticket_num in PROCESSING_TICKETS:
            PROCESSING_TICKETS.remove(ticket_num)
        if user_id_str in PROCESSING_USERS:
            PROCESSING_USERS.remove(user_id_str)

async def web_app_entry(update: Update, context: CallbackContext) -> int:
    """Handle data received from the Web App."""
    try:
        try:
            data = json.loads(update.effective_message.web_app_data.data)
        except json.JSONDecodeError as e:
            logger.error(f"JSON Decode Error in Web App data: {e}")
            await safe_reply(update, "❌ Ошибка: Некорректные данные от приложения (JSON Error).")
            return ConversationHandler.END
            
        user_id = update.effective_user.id
        user_name = update.effective_user.full_name
        
        # GAMIFICATION: Update user info
        user = update.effective_user
        await update_user_info(user.id, user.username, user.first_name, user.last_name)
        
        # Validate required fields
        required_fields = ['department_number', 'issue_number', 'ticket_number', 'date', 'region', 'items']
        if any(f not in data for f in required_fields):
            await safe_reply(update, "❌ Ошибка: Неполные данные.")
            return ConversationHandler.END

        # Validate region
        if data['region'] not in REGION_TOPICS:
             await safe_reply(update, "❌ Ошибка: Некорректный регион.")
             return ConversationHandler.END

        # Validate Date
        from datetime import datetime
        try:
            date_obj = datetime.strptime(data.get('date', ''), '%d.%m.%Y')
            if date_obj > datetime.now().replace(hour=0,minute=0,second=0,microsecond=0):
                await safe_reply(update, "⚠️ Ошибка: Будущая дата запрещена.")
                return ConversationHandler.END
        except ValueError:
             await safe_reply(update, "❌ Ошибка формата даты.")
             return ConversationHandler.END

        # Allow duplicates but skip points to keep stats clean.
        award_points = True
        if not data.get('is_test', False):
            dup_info = await check_ticket_duplicate(str(data['ticket_number']))
            if dup_info:
                award_points = False

        return await process_submission_data(update, context, data, user_id, user_name, award_points=award_points)

    except Exception as e:
        logger.error(f"Error processing Web App data: {e}", exc_info=True)
        await safe_reply(update, "❌ Произошла ошибка при обработке данных. Попробуйте еще раз.")
        return ConversationHandler.END

async def confirm_duplicate_handler(update: Update, context: CallbackContext) -> int:
    """Handle the confirmation for duplicate tickets."""
    query = update.callback_query
    await query.answer()
    
    choice = query.data
    user_id = update.effective_user.id
    user_name = update.effective_user.full_name
    
    if choice == "confirm_duplicate_yes":
        data = context.user_data.get('pending_web_data')
        if not data:
            await query.edit_message_text("❌ Ошибка: Данные устарели. Попробуйте снова.")
            return ConversationHandler.END
            
        await query.edit_message_text("🔄 Обработка подтверждена. Загружаю фото...")
        
        # Process without awarding points
        return await process_submission_data(update, context, data, user_id, user_name, award_points=False)
        
    else:
        # Cancelled
        context.user_data.pop('pending_web_data', None)
        await query.edit_message_text("❌ Отправка отменена.")
        return ConversationHandler.END

async def web_app_photo_handler(update: Update, context: CallbackContext) -> int:
    """Handle photos uploaded via Web App (legacy flow)."""
    user_id = update.effective_user.id
    data = await load_user_data(user_id)
    
    items = data.get('temp_items', [])
    current_photos = data.get('photo_desc', [])
    
    current_index = len(current_photos)
    
    if current_index >= len(items):
        await finalize_conclusion(context.bot, user_id, update.effective_user.full_name, data, send_to_group=True)
        return ConversationHandler.END

    # Process photo
    photo_file = await update.message.photo[-1].get_file()
    TEMP_PHOTOS_DIR.mkdir(parents=True, exist_ok=True)
    unique_name = generate_unique_filename()
    orig_path = TEMP_PHOTOS_DIR / f"orig_{unique_name}"
    comp_path = TEMP_PHOTOS_DIR / unique_name
    
    await photo_file.download_to_drive(orig_path)
    compress_image(orig_path, comp_path)
    if orig_path.exists():
        orig_path.unlink()
        
    # Add to photo_desc
    current_item = items[current_index]
    data['photo_desc'].append({
        'photo': str(comp_path),
        'description': current_item['description'],
        'evaluation': current_item['evaluation']
    })
    
    await save_user_data(user_id, data)
    
    # Check if we need more photos
    next_index = current_index + 1
    if next_index < len(items):
        next_item = items[next_index]
        await safe_reply(
            update, 
            f"✅ Фото принято.\n\n"
            f"📸 Отправьте фото для предмета №{next_index + 1}:\n"
            f"<b>{next_item['description']}</b> ({next_item['evaluation']} руб.)",
            parse_mode="HTML"
        )
        return WEB_APP_PHOTO
    else:
        # All photos received
        await safe_reply(update, "✅ Все фото получены! Формирую документ...")
        await finalize_conclusion(context.bot, user_id, update.effective_user.full_name, data, send_to_group=True)
        return ConversationHandler.END

async def get_department(update: Update, context: CallbackContext) -> int:
    """Handle department number input."""
    if not is_digit(update.message.text):
        await safe_reply(update, "Только цифры, пожалуйста.")
        return DEPARTMENT
    
    user_id = update.message.from_user.id
    data = await load_user_data(user_id)
    data['department_number'] = update.message.text
    await save_user_data(user_id, data)
    
    await stream_safe_reply(update, f"✅ Сохранено.\n\n🟡 {format_progress('issue')}\nВведите номер заключения:")
    return ISSUE_NUMBER

async def get_issue_number(update: Update, context: CallbackContext) -> int:
    """Handle issue number input."""
    if not is_digit(update.message.text):
        await safe_reply(update, "Только цифры, пожалуйста.")
        return ISSUE_NUMBER
        
    user_id = update.message.from_user.id
    data = await load_user_data(user_id)
    data['issue_number'] = update.message.text
    await save_user_data(user_id, data)
    
    await stream_safe_reply(update, f"✅ Сохранено.\n\n🟡 {format_progress('ticket')}\nВведите номер билета:")
    return TICKET_NUMBER

async def get_ticket_number(update: Update, context: CallbackContext) -> int:
    """Handle ticket number input."""
    if not is_valid_ticket_number(update.message.text):
        await safe_reply(update, "Неверный формат номера билета.")
        return TICKET_NUMBER
        
    user_id = update.message.from_user.id
    data = await load_user_data(user_id)
    data['ticket_number'] = update.message.text
    await save_user_data(user_id, data)
    
    await stream_safe_reply(update, f"✅ Сохранено.\n\n🟡 {format_progress('date')}\nВведите дату (ДД.ММ.ГГГГ):")
    return DATE

async def get_date(update: Update, context: CallbackContext) -> int:
    """Handle date input."""
    from datetime import datetime
    
    date_text = update.message.text.strip()
    
    # Validate date format and value
    try:
        date_obj = datetime.strptime(date_text, '%d.%m.%Y')
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        
        if date_obj > today:
            await safe_reply(update, "❌ Нельзя выбрать будущую дату. Введите сегодняшнюю или прошедшую дату (ДД.ММ.ГГГГ):")
            return DATE
    except ValueError:
        await safe_reply(update, "❌ Неверный формат даты. Используйте формат ДД.ММ.ГГГГ (например, 29.11.2025):")
        return DATE
    
    user_id = update.message.from_user.id
    data = await load_user_data(user_id)
    data['date'] = date_text
    await save_user_data(user_id, data)
    
    regions = [[f"🌍 {r}"] for r in REGION_TOPICS.keys()]
    markup = ReplyKeyboardMarkup(regions, one_time_keyboard=True, resize_keyboard=True)
    await stream_safe_reply(update, f"✅ Сохранено.\n\n🟡 {format_progress('region')}\nВыберите регион:", reply_markup=markup)
    return REGION

async def get_region(update: Update, context: CallbackContext) -> int:
    """Handle region selection."""
    region = normalize_region_input(update.message.text)
    if not region:
        await safe_reply(update, "Пожалуйста, выберите корректный регион.")
        return REGION
        
    user_id = update.message.from_user.id
    data = await load_user_data(user_id)
    data['region'] = region
    await save_user_data(user_id, data)
    
    await stream_safe_reply(
        update, 
        f"✅ Сохранено.\n\n🟡 {format_progress('photo')}\nОтправьте фото.\n{PHOTO_REQUIREMENTS_MESSAGE}",
        reply_markup=ReplyKeyboardRemove()
    )
    return PHOTO

async def photo_handler(update: Update, context: CallbackContext) -> int:
    """Handle photo upload."""
    user_id = update.message.from_user.id
    photo_file = await update.message.photo[-1].get_file()
    
    TEMP_PHOTOS_DIR.mkdir(parents=True, exist_ok=True)
    unique_name = generate_unique_filename()
    orig_path = TEMP_PHOTOS_DIR / f"orig_{unique_name}"
    comp_path = TEMP_PHOTOS_DIR / unique_name
    
    await photo_file.download_to_drive(orig_path)
    compress_image(orig_path, comp_path)
    if orig_path.exists():
        orig_path.unlink()
        
    data = await load_user_data(user_id)
    data.setdefault('photo_desc', []).append({'photo': str(comp_path), 'description': '', 'evaluation': ''})
    await save_user_data(user_id, data)
    
    await stream_safe_reply(update, f"✅ Фото получено.\n\n✏️ Введите описание:")
    return DESCRIPTION

async def description_handler(update: Update, context: CallbackContext) -> int:
    """Handle item description input."""
    user_id = update.message.from_user.id
    data = await load_user_data(user_id)
    if data.get('photo_desc'):
        data['photo_desc'][-1]['description'] = update.message.text
    await save_user_data(user_id, data)
    
    await stream_safe_reply(update, f"✅ Сохранено.\n\n💰 Введите оценку (цифры):")
    return EVALUATION

async def evaluation_handler(update: Update, context: CallbackContext) -> int:
    """Handle item evaluation (price) input."""
    if not is_digit(update.message.text):
        await safe_reply(update, "Только цифры.")
        return EVALUATION
        
    user_id = update.message.from_user.id
    data = await load_user_data(user_id)
    if data.get('photo_desc'):
        data['photo_desc'][-1]['evaluation'] = update.message.text
    await save_user_data(user_id, data)
    
    markup = ReplyKeyboardMarkup([["Да", "Нет"]], one_time_keyboard=True, resize_keyboard=True)
    await stream_safe_reply(update, "Добавить еще предмет?", reply_markup=markup)
    return MORE_PHOTO

async def more_photo_handler(update: Update, context: CallbackContext) -> int:
    """Handle 'add more photos' decision."""
    user_id = update.message.from_user.id
    
    if "да" in update.message.text.lower():
        # Check if we've reached the limit
        data = await load_user_data(user_id)
        current_photos = len(data.get('photo_desc', []))
        
        if current_photos >= MAX_PHOTOS:
            await safe_reply(
                update, 
                f"⚠️ Достигнут лимит предметов ({MAX_PHOTOS} шт.).\n\n"
                "Выберите режим:",
                reply_markup=ReplyKeyboardMarkup([["Тест", "Финал"]], one_time_keyboard=True, resize_keyboard=True)
            )
            return TESTING
        
        await safe_reply(update, "Отправьте фото следующего предмета.", reply_markup=ReplyKeyboardRemove())
        return PHOTO
    
    markup = ReplyKeyboardMarkup([["Тест", "Финал"]], one_time_keyboard=True, resize_keyboard=True)
    await safe_reply(update, "Выберите режим:", reply_markup=markup)
    return TESTING

async def testing_handler(update: Update, context: CallbackContext) -> int:
    """Handle final mode selection (Test/Final)."""
    user_id = update.message.from_user.id
    mode = update.message.text.lower()
    
    await safe_reply(update, "Генерирую документ...", reply_markup=ReplyKeyboardRemove())
    
    try:
        # CRITICAL: Validate date is not in the future
        from datetime import datetime
        data = await load_user_data(user_id)
        date_str = data.get('date', '')
        
        try:
            date_obj = datetime.strptime(date_str, '%d.%m.%Y')
            today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            
            if date_obj > today:
                logger.warning(f"Rejected future date in conversation: {date_str}")
                await safe_reply(update, "⚠️ Ошибка: Нельзя выбрать будущую дату!\n\nВыберите сегодняшнюю или прошедшую дату и начните заново (/start)")
                return ConversationHandler.END
        except ValueError:
            pass  # If date is invalid, let it pass for now (will be caught later)
        
        if "финал" in mode:
            award_points = True
            ticket_number = str(data.get('ticket_number', '')).strip()
            if ticket_number:
                dup_info = await check_ticket_duplicate(ticket_number)
                if dup_info:
                    award_points = False
                    await safe_reply(update, "⚠️ Дубликат билета: заключение сформировано, но баллы не начисляются.")

            await finalize_conclusion(
                context.bot,
                user_id,
                update.message.from_user.full_name,
                data,
                send_to_group=True,
                award_points=award_points
            )
            ticket_num = str(data.get('ticket_number', ''))
            issue_num = str(data.get('issue_number', ''))
            copy_keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("📋 Скопировать № билета", copy_text=CopyTextButton(text=ticket_num))],
                [InlineKeyboardButton("📋 Скопировать № заключения", copy_text=CopyTextButton(text=issue_num))]
            ])
            await safe_reply(
                update, 
                f"✅ Заключение сформировано и отправлено.\n"
                f"🎫 Билет: {ticket_num}\n"
                f"📝 Заключение: {issue_num}",
                reply_markup=copy_keyboard
            )
        else:
            path = await create_document(user_id, update.message.from_user.full_name)
            await send_document_from_path(context.bot, user_id, path, caption="🧪 Тестовый документ")
            if path.exists():
                path.unlink()
            
    except Exception as e:
        logger.error(f"Error: {e}")
        await safe_reply(update, "Ошибка генерации документа.")
        
    return ConversationHandler.END

async def cancel_handler(update: Update, context: CallbackContext) -> int:
    await safe_reply(update, "Отменено.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

def get_conversation_handler():
    return ConversationHandler(
        entry_points=[
            CommandHandler("start_chat", start_conversation),
            MessageHandler(filters.StatusUpdate.WEB_APP_DATA, web_app_entry)
        ],
        states={
            DEPARTMENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_department)],
            ISSUE_NUMBER: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_issue_number)],
            TICKET_NUMBER: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_ticket_number)],
            DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_date)],
            REGION: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_region)],
            PHOTO: [MessageHandler(filters.PHOTO, photo_handler)],
            DESCRIPTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, description_handler)],
            EVALUATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, evaluation_handler)],
            MORE_PHOTO: [MessageHandler(filters.TEXT & ~filters.COMMAND, more_photo_handler)],
            TESTING: [MessageHandler(filters.TEXT & ~filters.COMMAND, testing_handler)],
            WEB_APP_PHOTO: [MessageHandler(filters.PHOTO, web_app_photo_handler)],
            CONFIRM_DUPLICATE: [CallbackQueryHandler(confirm_duplicate_handler)],
        },
        fallbacks=[CommandHandler("cancel", cancel_handler)]
    )
