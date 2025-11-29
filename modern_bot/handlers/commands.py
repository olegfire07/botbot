import logging
from telegram import Update, WebAppInfo, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import ContextTypes
from modern_bot.handlers.admin import is_admin
from modern_bot.handlers.menu_helper import get_main_menu_keyboard

logger = logging.getLogger(__name__)

async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Sends a welcome message with a menu (ReplyKeyboard).
    """
    user = update.effective_user
    user_is_admin = is_admin(user.id)
    logger.info(f"⭐ User ID: {user.id} | Name: {user.full_name} | Is Admin: {user_is_admin}")

    reply_markup = get_main_menu_keyboard(user.id)

    await update.message.reply_text(
        f"Привет, {user.full_name}! 👋\n\n"
        "Я бот для создания заключений. \n"
        "Нажмите кнопку ниже, чтобы открыть форму.",
        reply_markup=reply_markup
    )

async def help_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Sends help instructions.
    """
    user_id = update.effective_user.id
    
    # General Help
    text = (
        "<b>ℹ️ Как пользоваться ботом:</b>\n\n"
        "1. Нажмите кнопку <b>📝 Создать заключение</b>.\n"
        "2. Заполните форму (номер билета, предметы, фото).\n"
        "3. Выберите режим: <b>Черновик</b> (для проверки) или <b>Оригинал</b> (в группу).\n"
        "4. Нажмите <b>Отправить</b>.\n\n"
        "Бот сформирует документ Word и пришлет его вам."
    )

    # Admin Help
    if is_admin(user_id):
        text += (
            "\n\n<b>👮‍♂️ Команды администратора:</b>\n"
            "/add_admin [ID] - Добавить админа\n"
            "/broadcast [текст] - Рассылка всем пользователям\n"
            "/history - Скачать историю (Excel)\n"
            "/download_month - Скачать архив за месяц"
        )

    # Show menu again
    await send_main_menu(update, text)

async def menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Shows main menu with buttons (same as /start).
    """
    reply_markup = get_main_menu_keyboard(update.effective_user.id)
    await update.message.reply_text(
        "📱 Главное меню:",
        reply_markup=reply_markup
    )

async def send_main_menu(update: Update, message_text: str):
    """Helper to send menu with keyboard."""
    reply_markup = get_main_menu_keyboard(update.effective_user.id)
    await update.message.reply_html(
        message_text,
        reply_markup=reply_markup
    )

async def old_mode_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handler for the 'Old Mode' button.
    """
    await update.message.reply_text(
        "Старый режим работы через диалог пока отключен.\n"
        "Пожалуйста, используйте кнопку '📝 Создать заключение' для удобного заполнения формы."
    )
