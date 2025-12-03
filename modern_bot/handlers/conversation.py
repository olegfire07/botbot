import logging
import json
import asyncio
import httpx
from pathlib import Path
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, InputMediaPhoto
from telegram.ext import CallbackContext, ConversationHandler, CommandHandler, MessageHandler, filters
from modern_bot.config import (
    PROGRESS_STEPS, TOTAL_STEPS, MAX_PHOTOS, MAX_PHOTO_SIZE_MB, 
    PHOTO_REQUIREMENTS_MESSAGE, REGION_TOPICS, MAIN_GROUP_CHAT_ID, TEMP_PHOTOS_DIR
)
from modern_bot.utils.validators import is_digit, is_valid_ticket_number, normalize_region_input
from modern_bot.utils.files import generate_unique_filename, compress_image, is_image_too_large
from modern_bot.database.db import save_user_data, load_user_data, delete_user_data
from modern_bot.services.docx_gen import create_document
from modern_bot.services.excel import update_excel
from modern_bot.services.archive import archive_document
from modern_bot.handlers.common import safe_reply, send_document_from_path
from modern_bot.services.flow import finalize_conclusion

logger = logging.getLogger(__name__)

(DEPARTMENT, ISSUE_NUMBER, TICKET_NUMBER, DATE, REGION, PHOTO, DESCRIPTION, EVALUATION,
 MORE_PHOTO, CONFIRMATION, TESTING, WEB_APP_PHOTO) = range(12)

def format_progress(stage: str) -> str:
    """Format the progress step string."""
    step = PROGRESS_STEPS.get(stage)
    return f"Шаг {step}/{TOTAL_STEPS}" if step else ""

async def start_conversation(update: Update, context: CallbackContext) -> int:
    """Start the conversation flow."""
    user = update.effective_user
    await delete_user_data(user.id)
    await save_user_data(user.id, {'photo_desc': []})
    
    await safe_reply(
        update,
        f"👋 Привет! Начнем создание нового заключения.\n\n"
        f"🟡 {format_progress('department')}\nВведите номер подразделения:"
    )
    return DEPARTMENT

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
        
        # Validate required fields
        required_fields = ['department_number', 'issue_number', 'ticket_number', 'date', 'region', 'items']
        missing_fields = [field for field in required_fields if field not in data]
        if missing_fields:
            logger.error(f"Web App data missing fields: {missing_fields}")
            await safe_reply(update, f"❌ Ошибка: Неполные данные. Отсутствуют: {', '.join(missing_fields)}")
            return ConversationHandler.END

        # Validate types/values
        if not str(data['department_number']).isdigit():
             await safe_reply(update, "❌ Ошибка: Номер подразделения должен быть числом.")
             return ConversationHandler.END
             
        if not str(data['issue_number']).isdigit():
             await safe_reply(update, "❌ Ошибка: Номер заключения должен быть числом.")
             return ConversationHandler.END

        # Validate region
        if data['region'] not in REGION_TOPICS:
             await safe_reply(update, "❌ Ошибка: Некорректный регион.")
             return ConversationHandler.END

        # Prepare data structure
        db_data = {
            'department_number': str(data['department_number']),
            'issue_number': str(data['issue_number']),
            'ticket_number': str(data['ticket_number']),
            'date': data['date'],
            'region': data['region'],
            'photo_desc': []
        }
        
        # CRITICAL: Validate date is not in the future
        from datetime import datetime
        date_str = data.get('date', '')
        try:
            date_obj = datetime.strptime(date_str, '%d.%m.%Y')
            today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            
            if date_obj > today:
                logger.warning(f"Rejected future date in Web App: {date_str} from user {user_id}")
                await safe_reply(update, "⚠️ Ошибка: Нельзя выбрать будущую дату!\n\nВыберите сегодняшнюю или прошедшую дату и попробуйте снова.")
                return ConversationHandler.END
        except ValueError as e:
            logger.error(f"Invalid date format in Web App: {date_str} - {e}")
            await safe_reply(update, "❌ Ошибка: Неверный формат даты. Используйте ДД.ММ.ГГГГ")
            return ConversationHandler.END
        
        # Process items and download photos
        TEMP_PHOTOS_DIR.mkdir(parents=True, exist_ok=True)
        
        items = data.get('items', [])
        if len(items) > MAX_PHOTOS:
            logger.warning("Received %s items, trimming to MAX_PHOTOS=%s", len(items), MAX_PHOTOS)
            items = items[:MAX_PHOTOS]

        max_photo_bytes = MAX_PHOTO_SIZE_MB * 1024 * 1024
        http_timeout = httpx.Timeout(10.0)
        http_limits = httpx.Limits(max_connections=4, max_keepalive_connections=2)
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }

        logger.info(f"Processing {len(items)} items with photos from Web App")
        async with httpx.AsyncClient(timeout=http_timeout, limits=http_limits, headers=headers, follow_redirects=True) as client:
            for idx, item in enumerate(items, 1):
                photo_url = item.get('photo_url')
                description = item.get('description')
                evaluation = item.get('evaluation')
                
                logger.info(f"Item {idx}/{len(items)}: photo_url={photo_url[:50] if photo_url else 'None'}..., description={description}, evaluation={evaluation}")
                
                if photo_url:
                    # Retry logic
                    for attempt in range(3):
                        try:
                            logger.info(f"Downloading photo from {photo_url} (Attempt {attempt+1}/3)")
                            response = await client.get(photo_url)
                            
                            if response.status_code != 200:
                                logger.error(f"Failed to download photo from {photo_url}: {response.status_code}")
                                if attempt < 2:
                                    await asyncio.sleep(1)
                                    continue
                                break

                            content_type = response.headers.get("Content-Type", "")
                            content_length = response.headers.get("Content-Length")

                            if not content_type.startswith("image/"):
                                logger.error(f"Invalid content type for {photo_url}: {content_type}")
                                break
                            
                            if content_length and int(content_length) > max_photo_bytes:
                                logger.error(f"Photo too large (header) {photo_url}: {content_length} bytes")
                                break
                                
                            if len(response.content) > max_photo_bytes:
                                logger.error(f"Photo too large (body) {photo_url}: {len(response.content)} bytes")
                                break

                            unique_name = generate_unique_filename()
                            file_path = TEMP_PHOTOS_DIR / unique_name

                            # Asynchronous file write
                            await asyncio.to_thread(file_path.write_bytes, response.content)
                            
                            logger.info(f"Photo saved successfully, size: {file_path.stat().st_size} bytes")
                            
                            photo_entry = {
                                'photo': str(file_path),
                                'description': description,
                                'evaluation': evaluation
                            }
                            db_data['photo_desc'].append(photo_entry)
                            logger.info(f"Added photo entry to db_data: {photo_entry}")
                            break # Success, exit retry loop
                            
                        except httpx.TimeoutException as e:
                            logger.error(f"Timeout downloading photo (Attempt {attempt+1}/3): {e}")
                            if attempt < 2:
                                await asyncio.sleep(2)
                                continue
                        except Exception as e:
                            logger.error(f"Error downloading photo (Attempt {attempt+1}/3): {e}", exc_info=True)
                            if attempt < 2:
                                await asyncio.sleep(1)
                                continue
                else:
                    logger.warning(f"No photo URL for item {idx}")
        
        await save_user_data(user_id, db_data)
        
        # Finalize immediately
        is_test = data.get('is_test', False)
        await safe_reply(update, f"✅ Данные получены! Формирую документ... {'(Тестовый режим)' if is_test else ''}")
        await finalize_conclusion(context.bot, user_id, user_name, db_data, send_to_group=(not is_test))
        return ConversationHandler.END

    except Exception as e:
        logger.error(f"Error processing Web App data: {e}", exc_info=True)
        await safe_reply(update, "❌ Произошла ошибка при обработке данных. Попробуйте еще раз.")
        return ConversationHandler.END

async def web_app_photo_handler(update: Update, context: CallbackContext) -> int:
    """Handle photos uploaded via Web App (legacy flow)."""
    user_id = update.effective_user.id
    data = await load_user_data(user_id)
    
    items = data.get('temp_items', [])
    current_photos = data.get('photo_desc', [])
    
    current_index = len(current_photos)
    
    if current_index >= len(items):
        # Should not happen ideally
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
    
    await safe_reply(update, f"✅ Сохранено.\n\n🟡 {format_progress('issue')}\nВведите номер заключения:")
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
    
    await safe_reply(update, f"✅ Сохранено.\n\n🟡 {format_progress('ticket')}\nВведите номер билета:")
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
    
    await safe_reply(update, f"✅ Сохранено.\n\n🟡 {format_progress('date')}\nВведите дату (ДД.ММ.ГГГГ):")
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
    await safe_reply(update, f"✅ Сохранено.\n\n🟡 {format_progress('region')}\nВыберите регион:", reply_markup=markup)
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
    
    await safe_reply(
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
    
    await safe_reply(update, f"✅ Фото получено.\n\n✏️ Введите описание:")
    return DESCRIPTION

async def description_handler(update: Update, context: CallbackContext) -> int:
    """Handle item description input."""
    user_id = update.message.from_user.id
    data = await load_user_data(user_id)
    if data.get('photo_desc'):
        data['photo_desc'][-1]['description'] = update.message.text
    await save_user_data(user_id, data)
    
    await safe_reply(update, f"✅ Сохранено.\n\n💰 Введите оценку (цифры):")
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
    await safe_reply(update, "Добавить еще фото?", reply_markup=markup)
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
                f"⚠️ Достигнут лимит фотографий ({MAX_PHOTOS} шт.).\n\n"
                "Выберите режим:",
                reply_markup=ReplyKeyboardMarkup([["Тест", "Финал"]], one_time_keyboard=True, resize_keyboard=True)
            )
            return TESTING
        
        await safe_reply(update, "Отправьте следующее фото.", reply_markup=ReplyKeyboardRemove())
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
            await finalize_conclusion(context.bot, user_id, update.message.from_user.full_name, data, send_to_group=True)
            await safe_reply(update, "✅ Заключение сформировано и отправлено.")
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
        },
        fallbacks=[CommandHandler("cancel", cancel_handler)]
    )
