"""
Helper module for showing persistent menu keyboard.
"""
import os
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, WebAppInfo
from modern_bot.handlers.admin import is_admin
from modern_bot.config import IMGBB_KEY

async def get_main_menu_keyboard(user_id: int) -> ReplyKeyboardMarkup:
    """
    Returns the main menu keyboard with injected theme and cache versioning.
    """
    from modern_bot.database.db import get_setting
    
    theme = await get_setting('current_theme', 'default')
    cv = await get_setting('cache_version', '1')
    
    base_url = os.getenv("WEB_APP_URL", "https://olegfire07.github.io/BestBOT/").strip()
    url_parts = urlsplit(base_url)
    query = dict(parse_qsl(url_parts.query, keep_blank_values=True))
    
    # Injected Parameters for "Offline-Aware" loading
    query["v"] = os.getenv("WEB_APP_VERSION", "5.1")
    query["theme"] = theme
    query["cv"] = cv
    
    if IMGBB_KEY:
        query["imgbb_key"] = IMGBB_KEY

    imageban_client = os.getenv("IMAGEBAN_CLIENT_ID", "").strip()
    if imageban_client:
        query["imageban_client"] = imageban_client

    bot_url = os.getenv("BOT_URL", "").strip()
    if bot_url:
        if bot_url == "localhost:8080":
            bot_url = "127.0.0.1:8080"
        if not bot_url.startswith(("http://", "https://")):
            bot_url = f"http://{bot_url}"
        query["bot_url"] = bot_url.rstrip("/")
        
    web_app_url = urlunsplit(
        (url_parts.scheme, url_parts.netloc, url_parts.path, urlencode(query), url_parts.fragment)
    )
    
    keyboard = [
        [KeyboardButton("📝 Новое заключение", web_app=WebAppInfo(url=web_app_url))],
        [KeyboardButton("🏆 Мой рейтинг"), KeyboardButton("ℹ️ Помощь")]
    ]
    
    if is_admin(user_id):
        keyboard.append([KeyboardButton("⚙️ Админ-панель")])
    
    return ReplyKeyboardMarkup(
        keyboard,
        resize_keyboard=True,
        input_field_placeholder="Выберите действие..."
    )

async def show_menu_after_action(update: Update, message_text: str = None):
    """
    Shows the main menu keyboard after an action.
    If message_text is provided, sends it. Otherwise just updates the keyboard.
    """
    user_id = update.effective_user.id
    keyboard = await get_main_menu_keyboard(user_id)
    
    if message_text:
        await update.message.reply_text(
            message_text,
            reply_markup=keyboard,
            parse_mode="HTML"
        )
    else:
        # Just update keyboard without sending a message
        await update.message.reply_text(
            "👌",
            reply_markup=keyboard
        )
