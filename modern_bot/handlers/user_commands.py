import logging
from telegram import Update
from telegram.ext import CallbackContext
from modern_bot.handlers.admin import is_admin, admin_ids, save_admin_ids
from modern_bot.handlers.common import safe_reply
from modern_bot.handlers.user_management import add_user_by_id, remove_user_by_id

logger = logging.getLogger(__name__)

async def add_user_command(update: Update, context: CallbackContext) -> None:
    """Add user by ID."""
    requester_id = update.effective_user.id
    
    if not is_admin(requester_id):
        await safe_reply(update, "❌ Доступ запрещен.")
        return
    
    if not context.args:
        await safe_reply(update, "Использование: /add_user <USER_ID>")
        return
    
    try:
        user_id = int(context.args[0])
    except ValueError:
        await safe_reply(update, "❌ ID должен быть числом.")
        return
    
    result = await add_user_by_id(user_id, requester_id)
    await safe_reply(update, result)

async def remove_user_command(update: Update, context: CallbackContext) -> None:
    """Remove user by ID."""
    requester_id = update.effective_user.id
    
    if not is_admin(requester_id):
        await safe_reply(update, "❌ Доступ запрещен.")
        return
    
    if not context.args:
        await safe_reply(update, "Использование: /remove_user <USER_ID>")
        return
    
    try:
        user_id = int(context.args[0])
    except ValueError:
        await safe_reply(update, "❌ ID должен быть числом.")
        return
    
    result = await remove_user_by_id(user_id, requester_id)
    await safe_reply(update, result)

async def remove_admin_command(update: Update, context: CallbackContext) -> None:
    """Remove admin by ID."""
    requester_id = update.effective_user.id
    
    if not is_admin(requester_id):
        await safe_reply(update, "❌ Доступ запрещен.")
        return
    
    if not context.args:
        await safe_reply(update, "Использование: /remove_admin <USER_ID>")
        return
    
    try:
        target_id = int(context.args[0])
    except ValueError:
        await safe_reply(update, "❌ ID должен быть числом.")
        return
    
    # Can't remove yourself
    if target_id == requester_id:
        await safe_reply(update, "❌ Нельзя удалить себя из админов.")
        return

    # Can't remove Super Admin
    if target_id == 2064900:
        await safe_reply(update, "❌ Нельзя удалить Супер-Админа.")
        return
    
    # Can't remove if not in list
    if target_id not in admin_ids:
        await safe_reply(update, f"ℹ️ Пользователь {target_id} не является администратором.")
        return
    
    # Remove
    admin_ids.remove(target_id)
    save_admin_ids()
    await safe_reply(update, f"✅ Администратор {target_id} удалён.")
