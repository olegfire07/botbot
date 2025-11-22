import json
import logging
from telegram import Update, BotCommand, BotCommandScopeChat
from telegram.ext import CallbackContext
from modern_bot.config import ADMIN_FILE, DEFAULT_ADMIN_IDS
from modern_bot.handlers.common import safe_reply

logger = logging.getLogger(__name__)
admin_ids = set()

def load_admin_ids() -> None:
    global admin_ids
    ids = set()
    if ADMIN_FILE.exists():
        try:
            with ADMIN_FILE.open("r", encoding="utf-8") as f:
                data = json.load(f)
            ids = {int(item) for item in data if isinstance(item, int) or (isinstance(item, str) and item.isdigit())}
        except (OSError, json.JSONDecodeError) as err:
            logger.warning(f"Failed to read admin list: {err}")
    if not ids:
        ids = set(DEFAULT_ADMIN_IDS)
        admin_ids = ids
        save_admin_ids()
    else:
        admin_ids = ids

def save_admin_ids() -> None:
    ADMIN_FILE.parent.mkdir(parents=True, exist_ok=True)
    with ADMIN_FILE.open("w", encoding="utf-8") as f:
        json.dump(sorted(admin_ids), f, ensure_ascii=False, indent=2)

def is_admin(user_id: int) -> bool:
    return user_id in admin_ids

async def add_admin_handler(update: Update, context: CallbackContext) -> None:
    requester_id = update.message.from_user.id
    if not is_admin(requester_id):
        await safe_reply(update, "Access denied.")
        return

    if not context.args:
        await safe_reply(update, "Usage: /add_admin <USER_ID>")
        return

    try:
        new_admin_id = int(context.args[0])
    except ValueError:
        await safe_reply(update, "ID must be a number.")
        return

    if new_admin_id in admin_ids:
        await safe_reply(update, "User is already an admin.")
        return

    admin_ids.add(new_admin_id)
    save_admin_ids()
    await safe_reply(update, f"User {new_admin_id} added as admin.")

async def broadcast_handler(update: Update, context: CallbackContext) -> None:
    """Sends a message to all known users (placeholder implementation)."""
    if not is_admin(update.message.from_user.id):
        await safe_reply(update, "Access denied.")
        return
    
    # In a real implementation, we would iterate over all users in the DB.
    # For now, we just echo.
    message = " ".join(context.args)
    if not message:
        await safe_reply(update, "Usage: /broadcast <message>")
        return
        
    await safe_reply(update, f"Broadcast feature is ready to be linked to DB. Message: {message}")

async def help_admin_handler(update: Update, context: CallbackContext) -> None:
    if not is_admin(update.message.from_user.id):
        return

    text = (
        "🔧 Admin Help:\n"
        "/history - Last 10 records\n"
        "/stats - Global stats\n"
        "/download_month MM.YYYY [Region] - Download archive\n"
        "/stats_period DD.MM.YYYY DD.MM.YYYY [Region]\n"
        "/reports - Reports wizard\n"
        "/add_admin ID - Add new admin\n"
        "/broadcast Message - Send message to all users\n"
    )
    await safe_reply(update, text)
