import json
import logging
from telegram import Update, WebAppInfo
from telegram.ext import CallbackContext
from modern_bot.database.db import save_user_data
from modern_bot.handlers.common import safe_reply
from modern_bot.services.flow import finalize_conclusion
from modern_bot.config import TEMP_PHOTOS_DIR
from modern_bot.utils.files import generate_unique_filename

logger = logging.getLogger(__name__)

async def start_handler(update: Update, context: CallbackContext) -> None:
    # Simple welcome message without side (reply) menu
    await safe_reply(
        update,
        "👋 Добро пожаловать! Нажмите кнопку ниже, чтобы открыть форму создания заключения.",
        reply_markup=None
    )

# web_app_data_handler moved to conversation.py

async def photo_upload_handler(update: Update, context: CallbackContext) -> None:
    # Legacy / Unused now
    pass
