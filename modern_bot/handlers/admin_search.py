import logging
from pathlib import Path
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, CopyTextButton
from telegram.ext import CallbackContext, ConversationHandler, MessageHandler, filters
from modern_bot.handlers.common import safe_reply, send_document_from_path
from modern_bot.handlers.admin import is_admin
from modern_bot.config import ARCHIVE_DIR
import json

logger = logging.getLogger(__name__)

WAITING_FOR_TICKET = 0

async def start_ticket_search(update: Update, context: CallbackContext) -> int:
    """Start ticket search process."""
    query = update.callback_query
    if query:
        await query.answer()
    
    if not is_admin(update.effective_user.id):
        await safe_reply(update, "❌ Доступ запрещен.")
        return ConversationHandler.END

    await safe_reply(
        update, 
        "🔎 <b>Поиск заключения</b>\n\n"
        "Введите <b>номер билета</b> (11 цифр):\n\n"
        "Отправьте /cancel для отмены.",
        parse_mode="HTML"
    )
    return WAITING_FOR_TICKET

async def handle_ticket_input(update: Update, context: CallbackContext) -> int:
    """Handle ticket number and search for conclusion."""
    ticket_number = update.message.text.strip()
    
    # Clean ticket number (only digits)
    clean_ticket = "".join(filter(str.isdigit, ticket_number))
    
    if len(clean_ticket) != 11:
        await safe_reply(
            update, 
            f"❌ Неверный формат номера.\n\n"
            f"Получено: {len(clean_ticket)} цифр\n"
            f"Требуется: 11 цифр\n\n"
            f"Попробуйте еще раз:"
        )
        return WAITING_FOR_TICKET
    
    await safe_reply(update, f"🔍 Ищу заключение для билета <code>{clean_ticket}</code>...", parse_mode="HTML")
    
    # Search in archive index
    index_file = ARCHIVE_DIR / "index.json"
    found_files = []
    
    if index_file.exists():
        try:
            with index_file.open("r", encoding="utf-8") as f:
                index_data = json.load(f)
            
            for entry in index_data:
                if entry.get("ticket") == clean_ticket:
                    archive_path = ARCHIVE_DIR / entry.get("archive_path")
                    if archive_path.exists():
                        found_files.append({
                            "path": archive_path,
                            "date": entry.get("date", ""),
                            "mode": "Тестовое" if "test" in str(archive_path) else "Оригинал"
                        })
        except Exception as e:
            logger.error(f"Error reading archive index: {e}")
    
    if not found_files:
        await safe_reply(
            update, 
            f"❌ <b>Заключение не найдено</b>\n\n"
            f"Билет <code>{clean_ticket}</code> не найден в архиве.\n\n"
            f"Возможно:\n"
            f"• Заключение еще не создавалось\n"
            f"• Файл был удален из архива\n"
            f"• Номер билета указан неверно",
            parse_mode="HTML"
        )
        return ConversationHandler.END
    
    # Send all found files
    for idx, file_info in enumerate(found_files, 1):
        try:
            caption = (
                f"✅ <b>Заключение #{idx}</b>\n"
                f"📋 Билет: <code>{clean_ticket}</code>\n"
                f"📅 Дата: {file_info['date']}\n"
                f"📝 Тип: {file_info['mode']}"
            )
            await send_document_from_path(
                context.bot, 
                update.effective_chat.id, 
                file_info['path'],
                caption=caption,
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Error sending document: {e}")
            await safe_reply(update, f"⚠️ Ошибка отправки файла #{idx}")
    
    # Add copy button for the ticket number
    copy_keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📋 Скопировать номер билета", copy_text=CopyTextButton(text=clean_ticket))]
    ])
    
    if len(found_files) > 1:
        await safe_reply(
            update, 
            f"📊 Найдено заключений: {len(found_files)}\n"
            f"Все файлы отправлены выше.",
            reply_markup=copy_keyboard
        )
    else:
        await safe_reply(
            update,
            f"✅ Заключение для билета <code>{clean_ticket}</code> найдено и отправлено.",
            parse_mode="HTML",
            reply_markup=copy_keyboard
        )
    
    return ConversationHandler.END

async def cancel_search(update: Update, context: CallbackContext) -> int:
    """Cancel the search process."""
    await safe_reply(update, "❌ Поиск отменен.")
    return ConversationHandler.END
