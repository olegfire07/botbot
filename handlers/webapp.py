import json
from telegram import Update, ReplyKeyboardRemove
from telegram.ext import CallbackContext, ConversationHandler

from database.db import db
from handlers.common import PHOTO, PROGRESS_STEPS, TOTAL_STEPS
from utils.helpers import format_progress
from config.settings import settings
from utils.keyboards import build_keyboard_with_menu

async def webapp_data_handler(update: Update, context: CallbackContext) -> int:
    user_id = update.message.from_user.id
    
    # Parse data from Web App
    try:
        data_str = update.message.web_app_data.data
        web_data = json.loads(data_str)
    except (ValueError, AttributeError):
        await update.message.reply_text("❌ Ошибка получения данных из формы.")
        return ConversationHandler.END

    # Save to DB
    # We need to map web_data fields to our DB schema
    # Web data: department_number, issue_number, ticket_number, date, region, description, evaluation
    
    # First, save basic info
    db_data = {
        'department_number': web_data['department_number'],
        'issue_number': web_data['issue_number'],
        'ticket_number': web_data['ticket_number'],
        'date': web_data['date'],
        'region': web_data['region'],
        'photo_desc': [] # Reset photos
    }
    
    # Add the first item description/evaluation as a pending item or just save it?
    # Our logic expects photos first, then description.
    # But here we got description first.
    # Let's save the description/evaluation in a temporary way or just append it to the first photo when it arrives?
    # Better approach: Save it in user_data context and apply to the first photo.
    
    context.user_data['pending_desc'] = web_data['description']
    context.user_data['pending_eval'] = web_data['evaluation']
    
    # Also update user settings for persistence
    await db.update_user_settings(user_id, department=web_data['department_number'], region=web_data['region'])
    await db.save_user_data(user_id, db_data)

    PHOTO_REQUIREMENTS_MESSAGE = (
        "Требования к фото:\n"
        "• Формат JPG/PNG\n"
        f"• Размер до {settings.MAX_PHOTO_SIZE_MB} МБ\n"
        "• Минимальное разрешение 800×600"
    )

    await update.message.reply_text(
        f"✅ Данные из формы получены!\n\n"
        f"🟡 {format_progress('photo', PROGRESS_STEPS, TOTAL_STEPS)}\nТеперь отправьте фото предмета.\n"
        f"{PHOTO_REQUIREMENTS_MESSAGE}",
        reply_markup=ReplyKeyboardRemove()
    )
    
    return PHOTO
