import logging
from telegram import Update, WebAppInfo, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import ContextTypes
from modern_bot.config import ADMIN_IDS

logger = logging.getLogger(__name__)

async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Sends a welcome message with a menu (ReplyKeyboard).
    """
    user = update.effective_user
    logger.info(f"User {user.id} ({user.full_name}) started the bot.")

    # Web App URL (GitHub Pages)
    web_app_url = "https://olegfire07.github.io/botbot/?v=3"

    # Menu Buttons
    keyboard = [
        [KeyboardButton("📝 Создать заключение", web_app=WebAppInfo(url=web_app_url))],
        [KeyboardButton("ℹ️ Помощь"), KeyboardButton("📂 Старый режим")]
    ]
    
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

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
    if user_id in ADMIN_IDS:
        text += (
            "\n\n<b>👮‍♂️ Команды администратора:</b>\n"
            "/add_admin [ID] - Добавить админа\n"
            "/broadcast [текст] - Рассылка всем пользователям\n"
            "/history - Скачать историю (Excel)\n"
            "/download_month - Скачать архив за месяц"
        )

    await update.message.reply_html(text)

async def old_mode_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handler for the 'Old Mode' button.
    """
    await update.message.reply_text(
        "Старый режим работы через диалог пока отключен.\n"
        "Пожалуйста, используйте кнопку '📝 Создать заключение' для удобного заполнения формы."
    )
