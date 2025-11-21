from telegram import Update, ReplyKeyboardRemove
from telegram.ext import CallbackContext, ConversationHandler
from database.db import db
from utils.keyboards import build_keyboard_with_menu, build_main_menu
from utils.helpers import format_progress, ticket_digits_phrase
from config.settings import settings
from services.image import clean_temp_files

# Conversation states
(DEPARTMENT, ISSUE_NUMBER, TICKET_NUMBER, DATE, REGION, PHOTO, DESCRIPTION, EVALUATION,
 MORE_PHOTO, CONFIRMATION, TESTING, REPORT_ACTION, REPORT_MONTH_INPUT, REPORT_MONTH_REGION,
 REPORT_PERIOD_START, REPORT_PERIOD_END, REPORT_PERIOD_REGION) = range(17)

PROGRESS_STEPS = {
    "department": 1, "issue": 2, "ticket": 3, "date": 4, "region": 5,
    "photo": 6, "description": 7, "evaluation": 8, "summary": 9, "mode": 10
}
TOTAL_STEPS = 10

async def start_handler(update: Update, context: CallbackContext) -> int:
    user_id = update.message.from_user.id
    
    # Cleanup old data
    await db.delete_user_data(user_id)
    await db.save_user_data(user_id, {'photo_desc': []})
    
    # Load settings
    settings_data = await db.get_user_settings(user_id)
    last_dept = settings_data.get('last_department')
    
    markup = None
    if last_dept:
        markup = build_keyboard_with_menu([[f"Использовать: {last_dept}"], ["/cancel ❌Отмена"]], one_time=True)
    else:
        markup = build_keyboard_with_menu([["/cancel ❌Отмена"]], one_time=True)

    await update.message.reply_text(
        "👋 Привет! Я помогу создать заключение.\n\n"
        f"🟡 {format_progress('department', PROGRESS_STEPS, TOTAL_STEPS)}\nВведите номер подразделения (например: 385):",
        reply_markup=markup
    )
    return DEPARTMENT

async def cancel_handler(update: Update, context: CallbackContext) -> int:
    user_id = update.message.from_user.id
    await db.delete_user_data(user_id)
    await update.message.reply_text("❌ Процесс отменён. Для нового запуска введите /start.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

async def menu_handler(update: Update, context: CallbackContext) -> None:
    user_id = update.message.from_user.id
    # Load admin IDs dynamically if possible, or use default
    # Ideally we should have a service to get admin IDs. 
    # For now using settings.DEFAULT_ADMIN_IDS but we should probably load from file if we support adding admins
    from handlers.admin import load_admin_ids
    admin_ids = load_admin_ids()
    
    markup = build_main_menu(user_id, admin_ids)
    await update.message.reply_text("📋 Главное меню:", reply_markup=markup)

async def help_handler(update: Update, context: CallbackContext) -> None:
    message = (
        "📚 Инструкция по созданию заключения:\n\n"
        "1. ▶️ /start — укажите номер подразделения, номер заключения за день, номер билета "
        f"({ticket_digits_phrase()}), дату (ДД.ММ.ГГГГ) и выберите регион.\n"
        f"2. 📸 Для каждого предмета отправьте фото (JPG/PNG до {settings.MAX_PHOTO_SIZE_MB} МБ, минимум 800×600), затем добавьте краткое описание и оценку в рублях.\n"
        "3. ➕ Можно прикрепить несколько фото: после каждого изображения ответьте, нужно ли добавить ещё одно.\n"
        "4. 🔍 Перед подтверждением бот покажет сводку и превью последних снимков — проверьте данные.\n"
        "5. 📨 Выберите режим: ⚠️ Тестовое (файл придёт только вам) или ✅ Окончательное (документ отправится в рабочую группу и попадёт в отчёт).\n"
        "6. ❌ Команда /cancel прерывает текущий сценарий и очищает введённые данные.\n\n"
        "Нужно начать заново или попасть в меню? Нажмите /menu."
    )
    await update.message.reply_text(message)
