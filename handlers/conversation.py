from telegram import Update, ReplyKeyboardRemove, InputMediaPhoto, ReplyKeyboardMarkup
from telegram.ext import CallbackContext, ConversationHandler
from datetime import datetime
from pathlib import Path
import json

from config.settings import settings
from database.db import db
from utils.helpers import (
    is_digit, is_valid_ticket_number, ticket_digits_phrase, format_progress,
    generate_unique_filename, parse_date_str
)
from utils.keyboards import build_keyboard_with_menu, BACK_BUTTON_LABEL
from services.image import compress_image, is_image_too_large, clean_temp_files
from services.document import create_document
from services.excel import update_excel
from services.archive import archive_document
from handlers.common import (
    DEPARTMENT, ISSUE_NUMBER, TICKET_NUMBER, DATE, REGION, PHOTO, DESCRIPTION, EVALUATION,
    MORE_PHOTO, CONFIRMATION, TESTING
)

# Progress tracking helper
PROGRESS_STEPS = {
    "department": 1, "issue": 2, "ticket": 3, "date": 4, "region": 5,
    "photo": 6, "description": 7, "evaluation": 8, "summary": 9, "mode": 10
}
TOTAL_STEPS = 10

async def get_department(update: Update, context: CallbackContext) -> int:
    user_id = update.message.from_user.id
    text = update.message.text.strip()
    
    # Check for saved settings usage
    if text.startswith("Использовать:"):
        dept = text.split(":")[1].strip()
        text = dept

    if not is_digit(text):
        await update.message.reply_text("❗ Ошибка: номер должен содержать только цифры. Попробуйте снова:")
        return DEPARTMENT
        
    # Save settings
    await db.update_user_settings(user_id, department=text)
    
    data = await db.load_user_data(user_id)
    data['department_number'] = text
    await db.save_user_data(user_id, data)
    
    markup = build_keyboard_with_menu([], one_time=True, add_back=True)
    await update.message.reply_text(
        "✅ Номер подразделения принят.\n\n"
        f"🟡 {format_progress('issue', PROGRESS_STEPS, TOTAL_STEPS)}\nВведите порядковый номер заключения за день (например: 1):",
        reply_markup=markup
    )
    return ISSUE_NUMBER

async def get_issue_number(update: Update, context: CallbackContext) -> int:
    user_id = update.message.from_user.id
    text = update.message.text.strip()
    
    if text == BACK_BUTTON_LABEL:
        # Go back to Department
        settings_data = await db.get_user_settings(user_id)
        last_dept = settings_data.get('last_department')
        
        markup = None
        if last_dept:
            markup = build_keyboard_with_menu([[f"Использовать: {last_dept}"]], one_time=True)
        else:
            markup = build_keyboard_with_menu([], one_time=True)
            
        await update.message.reply_text(
            f"🟡 {format_progress('department', PROGRESS_STEPS, TOTAL_STEPS)}\nВведите номер подразделения (например: 385):",
            reply_markup=markup
        )
        return DEPARTMENT

    if not is_digit(text):
        await update.message.reply_text("❗ Ошибка: номер должен содержать только цифры. Введите снова:")
        return ISSUE_NUMBER
        
    data = await db.load_user_data(user_id)
    data['issue_number'] = text
    await db.save_user_data(user_id, data)
    
    markup = build_keyboard_with_menu([], one_time=True, add_back=True)
    await update.message.reply_text(
        "✅ Номер заключения сохранён.\n\n"
        f"🟡 {format_progress('ticket', PROGRESS_STEPS, TOTAL_STEPS)}\nВведите номер залогового билета "
        f"(например: 01230004567, {ticket_digits_phrase()}):",
        reply_markup=markup
    )
    return TICKET_NUMBER

async def get_ticket_number(update: Update, context: CallbackContext) -> int:
    user_id = update.message.from_user.id
    text = update.message.text.strip()
    
    if text == BACK_BUTTON_LABEL:
        markup = build_keyboard_with_menu([], one_time=True, add_back=True)
        await update.message.reply_text(
            f"🟡 {format_progress('issue', PROGRESS_STEPS, TOTAL_STEPS)}\nВведите порядковый номер заключения за день:",
            reply_markup=markup
        )
        return ISSUE_NUMBER

    if not is_valid_ticket_number(text):
        await update.message.reply_text(
            f"❗ Ошибка: номер билета должен содержать {ticket_digits_phrase()}. Введите снова:"
        )
        return TICKET_NUMBER
        
    data = await db.load_user_data(user_id)
    data['ticket_number'] = text
    await db.save_user_data(user_id, data)
    
    markup = build_keyboard_with_menu([], one_time=True, add_back=True)
    await update.message.reply_text(
        "✅ Номер билета сохранён.\n\n"
        f"🟡 {format_progress('date', PROGRESS_STEPS, TOTAL_STEPS)}\nВведите дату заключения (например: сегодня, 21.11, 01.03.2025):",
        reply_markup=markup
    )
    return DATE

async def get_date(update: Update, context: CallbackContext) -> int:
    user_id = update.message.from_user.id
    text = update.message.text.strip()
    
    if text == BACK_BUTTON_LABEL:
        markup = build_keyboard_with_menu([], one_time=True, add_back=True)
        await update.message.reply_text(
            f"🟡 {format_progress('ticket', PROGRESS_STEPS, TOTAL_STEPS)}\nВведите номер залогового билета:",
            reply_markup=markup
        )
        return TICKET_NUMBER

    date_obj = parse_date_str(text)
    if not date_obj:
        await update.message.reply_text("❗ Ошибка: неверный формат даты. Попробуйте 'сегодня', '21.11' или 'ДД.ММ.ГГГГ'.")
        return DATE
        
    date_str = date_obj.strftime("%d.%m.%Y")
    data = await db.load_user_data(user_id)
    data['date'] = date_str
    await db.save_user_data(user_id, data)
    
    # Prepare region suggestions
    settings_data = await db.get_user_settings(user_id)
    last_region = settings_data.get('last_region')
    
    region_rows = []
    if last_region and last_region in settings.REGION_TOPICS:
        region_rows.append([f"🌍 {last_region}"])
        
    for region in settings.REGION_TOPICS.keys():
        if region != last_region:
            region_rows.append([f"🌍 {region}"])
            
    markup = build_keyboard_with_menu(region_rows, one_time=True, add_back=True)
    await update.message.reply_text(
        f"✅ Дата сохранена: {date_str}\n\n"
        f"🟡 {format_progress('region', PROGRESS_STEPS, TOTAL_STEPS)}\nВыберите регион:",
        reply_markup=markup
    )
    return REGION

async def get_region(update: Update, context: CallbackContext) -> int:
    user_id = update.message.from_user.id
    text = update.message.text.strip()
    
    if text == BACK_BUTTON_LABEL:
        markup = build_keyboard_with_menu([], one_time=True, add_back=True)
        await update.message.reply_text(
            f"🟡 {format_progress('date', PROGRESS_STEPS, TOTAL_STEPS)}\nВведите дату заключения:",
            reply_markup=markup
        )
        return DATE

    region_text = text.split(" ", 1)[-1] # Remove emoji if present
    if region_text not in settings.REGION_TOPICS:
        await update.message.reply_text("❗ Ошибка: выберите регион из предложенных вариантов.")
        return REGION
        
    # Save settings
    await db.update_user_settings(user_id, region=region_text)
    
    data = await db.load_user_data(user_id)
    data['region'] = region_text
    await db.save_user_data(user_id, data)
    
    photo_count = len(data.get('photo_desc', []))
    
    PHOTO_REQUIREMENTS_MESSAGE = (
        "Требования к фото:\n"
        "• Формат JPG/PNG\n"
        f"• Размер до {settings.MAX_PHOTO_SIZE_MB} МБ\n"
        "• Минимальное разрешение 800×600"
    )
    
    markup = build_keyboard_with_menu([], one_time=True, add_back=True)
    await update.message.reply_text(
        "✅ Регион выбран.\n\n"
        f"🟡 {format_progress('photo', PROGRESS_STEPS, TOTAL_STEPS)}\nОтправьте фото предмета.\n"
        f"{PHOTO_REQUIREMENTS_MESSAGE}\n\n"
        f"(Загружено: {photo_count}/{settings.MAX_PHOTOS})",
        reply_markup=markup
    )
    return PHOTO

async def photo_handler(update: Update, context: CallbackContext) -> int:
    user_id = update.message.from_user.id
    message = update.message
    text = message.text.strip() if message.text else ""
    
    if text == BACK_BUTTON_LABEL:
        # Go back to Region
        settings_data = await db.get_user_settings(user_id)
        last_region = settings_data.get('last_region')
        region_rows = []
        if last_region and last_region in settings.REGION_TOPICS:
            region_rows.append([f"🌍 {last_region}"])
        for region in settings.REGION_TOPICS.keys():
            if region != last_region:
                region_rows.append([f"🌍 {region}"])
        markup = build_keyboard_with_menu(region_rows, one_time=True, add_back=True)
        await update.message.reply_text(
            f"🟡 {format_progress('region', PROGRESS_STEPS, TOTAL_STEPS)}\nВыберите регион:",
            reply_markup=markup
        )
        return REGION

    PHOTO_REQUIREMENTS_MESSAGE = (
        "Требования к фото:\n"
        "• Формат JPG/PNG\n"
        f"• Размер до {settings.MAX_PHOTO_SIZE_MB} МБ\n"
        "• Минимальное разрешение 800×600"
    )

    file_entity = None
    if message.photo:
        file_entity = message.photo[-1]
    elif message.document and getattr(message.document, "mime_type", "").startswith("image/"):
        file_entity = message.document
    
    if not file_entity:
        await update.message.reply_text(f"❗ Пришлите фото (JPG/PNG).\n\n{PHOTO_REQUIREMENTS_MESSAGE}")
        return PHOTO

    data = await db.load_user_data(user_id)
    if not data:
        data = {'photo_desc': []}
        await db.save_user_data(user_id, data)

    if len(data.get('photo_desc', [])) >= settings.MAX_PHOTOS:
        await update.message.reply_text(f"❗ Достигнут лимит в {settings.MAX_PHOTOS} фото.")
        return PHOTO

    settings.TEMP_PHOTOS_DIR.mkdir(parents=True, exist_ok=True)
    unique_name = generate_unique_filename()
    original_path = settings.TEMP_PHOTOS_DIR / f"orig_{unique_name}"
    compressed_path = settings.TEMP_PHOTOS_DIR / unique_name
    
    try:
        file = await file_entity.get_file()
        await file.download_to_drive(original_path)
        
        if is_image_too_large(original_path):
             await update.message.reply_text(f"❗ Файл слишком большой.\n\n{PHOTO_REQUIREMENTS_MESSAGE}")
             return PHOTO
             
        import asyncio
        await asyncio.to_thread(compress_image, original_path, compressed_path)
        
    except Exception as e:
        await update.message.reply_text("❌ Ошибка обработки фото. Попробуйте снова.")
        return PHOTO
    finally:
        if original_path.exists():
            original_path.unlink()

    data.setdefault('photo_desc', []).append({'photo': str(compressed_path), 'description': '', 'evaluation': ''})
    await db.save_user_data(user_id, data)

    markup = build_keyboard_with_menu([], one_time=True, add_back=True)
    await update.message.reply_text(
        f"✅ Фото получено! ({format_progress('description', PROGRESS_STEPS, TOTAL_STEPS)})\n✏️ Введите краткое описание предмета:",
        reply_markup=markup
    )
    return DESCRIPTION

async def description_handler(update: Update, context: CallbackContext) -> int:
    user_id = update.message.from_user.id
    text = update.message.text.strip()
    data = await db.load_user_data(user_id)
    
    if text == BACK_BUTTON_LABEL:
        # Remove last photo since we are going back
        if data.get('photo_desc'):
            last_photo = data['photo_desc'].pop()
            path = Path(last_photo.get('photo', ''))
            if path.exists():
                path.unlink()
            await db.save_user_data(user_id, data)
            
        photo_count = len(data.get('photo_desc', []))
        markup = build_keyboard_with_menu([], one_time=True, add_back=True)
        await update.message.reply_text(
            f"🟡 {format_progress('photo', PROGRESS_STEPS, TOTAL_STEPS)}\nОтправьте фото предмета.\n"
            f"(Загружено: {photo_count}/{settings.MAX_PHOTOS})",
            reply_markup=markup
        )
        return PHOTO

    if data.get('photo_desc'):
        data['photo_desc'][-1]['description'] = text
    await db.save_user_data(user_id, data)
    
    markup = build_keyboard_with_menu([], one_time=True, add_back=True)
    await update.message.reply_text(
        "✅ Описание сохранено.\n\n"
        f"💰 {format_progress('evaluation', PROGRESS_STEPS, TOTAL_STEPS)}\nВведите оценку предмета (целое число, например: 1500):",
        reply_markup=markup
    )
    return EVALUATION

async def evaluation_handler(update: Update, context: CallbackContext) -> int:
    user_id = update.message.from_user.id
    text = update.message.text.strip()
    
    if text == BACK_BUTTON_LABEL:
        markup = build_keyboard_with_menu([], one_time=True, add_back=True)
        await update.message.reply_text(
            f"✏️ {format_progress('description', PROGRESS_STEPS, TOTAL_STEPS)}\nВведите краткое описание предмета:",
            reply_markup=markup
        )
        return DESCRIPTION

    if not is_digit(text):
        await update.message.reply_text("❗ Ошибка: оценка должна быть целым числом. Введите снова:")
        return EVALUATION

    data = await db.load_user_data(user_id)
    if data.get('photo_desc'):
        data['photo_desc'][-1]['evaluation'] = text
    await db.save_user_data(user_id, data)

    photo_count = len(data.get('photo_desc', []))
    markup = build_keyboard_with_menu([["✅ Да, добавить фото"], ["❌ Нет, перейти к сводке"]], one_time=True, add_back=True)
    await update.message.reply_text(
        f"📷 {format_progress('photo', PROGRESS_STEPS, TOTAL_STEPS)} – добавить ещё одно фото? ({photo_count}/{settings.MAX_PHOTOS})",
        reply_markup=markup
    )
    return MORE_PHOTO

async def more_photo_handler(update: Update, context: CallbackContext) -> int:
    text = update.message.text.strip().lower()
    user_id = update.message.from_user.id
    
    if text == BACK_BUTTON_LABEL.lower():
        markup = build_keyboard_with_menu([], one_time=True, add_back=True)
        await update.message.reply_text(
            f"💰 {format_progress('evaluation', PROGRESS_STEPS, TOTAL_STEPS)}\nВведите оценку предмета:",
            reply_markup=markup
        )
        return EVALUATION

    if "да" in text:
        data = await db.load_user_data(user_id)
        photo_count = len(data.get('photo_desc', []))
        markup = build_keyboard_with_menu([], one_time=True, add_back=True)
        await update.message.reply_text(
            f"🟡 {format_progress('photo', PROGRESS_STEPS, TOTAL_STEPS)}\nОтправьте следующее фото.\n"
            f"(Загружено: {photo_count}/{settings.MAX_PHOTOS})",
            reply_markup=markup
        )
        return PHOTO

    data = await db.load_user_data(user_id)
    
    # Send previews
    photos = data.get('photo_desc', [])
    if photos:
        media_items = []
        for item in photos[-2:]: # Last 2
            path = Path(item.get('photo', ""))
            if path.is_file():
                caption = f"{item.get('description')}\n💰 {item.get('evaluation')} руб."
                media_items.append(InputMediaPhoto(open(path, 'rb'), caption=caption))
        if media_items:
             await update.message.reply_media_group(media_items)

    # Build summary
    total_value = sum(int(item.get('evaluation', 0)) for item in photos if is_digit(str(item.get('evaluation', 0))))
    summary = (
        f"Номер подразделения: {data.get('department_number')}\n"
        f"Номер заключения: {data.get('issue_number')}\n"
        f"Билет: {data.get('ticket_number')}\n"
        f"Дата: {data.get('date')}\n"
        f"Регион: {data.get('region')}\n"
        "---\n"
        f"Всего предметов: {len(photos)}\n"
        f"Сумма: {total_value}"
    )

    markup = build_keyboard_with_menu([["✅ Да, всё верно"], ["❌ Нет, отменить"]], one_time=True, add_back=True)
    await update.message.reply_text(
        f"🔍 {format_progress('summary', PROGRESS_STEPS, TOTAL_STEPS)} – проверьте данные:\n\n{summary}\n\nВсё верно?",
        reply_markup=markup
    )
    return CONFIRMATION

async def confirmation_handler(update: Update, context: CallbackContext) -> int:
    text = update.message.text.strip().lower()
    user_id = update.message.from_user.id
    
    if text == BACK_BUTTON_LABEL.lower():
        data = await db.load_user_data(user_id)
        photo_count = len(data.get('photo_desc', []))
        markup = build_keyboard_with_menu([["✅ Да, добавить фото"], ["❌ Нет, перейти к сводке"]], one_time=True, add_back=True)
        await update.message.reply_text(
            f"📷 {format_progress('photo', PROGRESS_STEPS, TOTAL_STEPS)} – добавить ещё одно фото? ({photo_count}/{settings.MAX_PHOTOS})",
            reply_markup=markup
        )
        return MORE_PHOTO

    if "да" in text:
        markup = build_keyboard_with_menu([["⚠️ Тестовое"], ["✅ Окончательное"]], one_time=True, add_back=True)
        await update.message.reply_text(
            f"🔚 {format_progress('mode', PROGRESS_STEPS, TOTAL_STEPS)} – выберите режим:\n"
            "   • ⚠️ Тестовое – документ придет только вам.\n"
            "   • ✅ Окончательное – документ отправится в группу.",
            reply_markup=markup
        )
        return TESTING

    await update.message.reply_text("Процесс отменён. Для нового запуска введите /start.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

async def test_choice_handler(update: Update, context: CallbackContext) -> int:
    user_id = update.message.from_user.id
    choice = update.message.text.strip().lower()
    
    if choice == BACK_BUTTON_LABEL.lower():
        data = await db.load_user_data(user_id)
        # Re-show summary
        photos = data.get('photo_desc', [])
        total_value = sum(int(item.get('evaluation', 0)) for item in photos if is_digit(str(item.get('evaluation', 0))))
        summary = (
            f"Номер подразделения: {data.get('department_number')}\n"
            f"Номер заключения: {data.get('issue_number')}\n"
            f"Билет: {data.get('ticket_number')}\n"
            f"Дата: {data.get('date')}\n"
            f"Регион: {data.get('region')}\n"
            "---\n"
            f"Всего предметов: {len(photos)}\n"
            f"Сумма: {total_value}"
        )
        markup = build_keyboard_with_menu([["✅ Да, всё верно"], ["❌ Нет, отменить"]], one_time=True, add_back=True)
        await update.message.reply_text(
            f"🔍 {format_progress('summary', PROGRESS_STEPS, TOTAL_STEPS)} – проверьте данные:\n\n{summary}\n\nВсё верно?",
            reply_markup=markup
        )
        return CONFIRMATION

    username = update.message.from_user.full_name
    await update.message.reply_text("⏳ Создаю документ...", reply_markup=ReplyKeyboardRemove())

    try:
        filename_path = await create_document(user_id, username)
        await update.message.reply_document(document=open(filename_path, 'rb'))

        if "окончательное" in choice:
            data = await db.load_user_data(user_id)
            region = data.get('region')
            if region and region in settings.REGION_TOPICS:
                topic_id = settings.REGION_TOPICS[region]
                caption = (f"Заключение от п. {data.get('department_number')}, "
                           f"билет: {data.get('ticket_number')}, от {data.get('date')}")
                
                try:
                    await context.bot.send_document(
                        chat_id=settings.MAIN_GROUP_CHAT_ID,
                        document=open(filename_path, 'rb'),
                        caption=caption,
                        message_thread_id=topic_id
                    )
                    await update.message.reply_text("✅ Документ отправлен в группу.")
                except Exception as e:
                    await update.message.reply_text(f"⚠️ Ошибка отправки в группу: {e}")

                try:
                    await update_excel(data)
                except Exception as e:
                    await update.message.reply_text(f"⚠️ Ошибка обновления Excel: {e}")

                try:
                    await archive_document(filename_path, data)
                except Exception as e:
                     await update.message.reply_text(f"⚠️ Ошибка архивации: {e}")
            else:
                await update.message.reply_text("❗ Ошибка: регион не найден.")
        else:
            await update.message.reply_text("ℹ️ Тестовое заключение создано.")

        if filename_path.exists():
            filename_path.unlink()
            
        data = await db.load_user_data(user_id)
        for item in data.get('photo_desc', []):
            path = Path(item.get('photo', ""))
            if path.exists():
                path.unlink()
        
        await db.delete_user_data(user_id)

    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")

    await update.message.reply_text("✅ Работа завершена. /start для нового.")
    return ConversationHandler.END
