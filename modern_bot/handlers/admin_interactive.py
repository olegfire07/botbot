import logging
from telegram import Update, ForceReply
from telegram.ext import CallbackContext
from modern_bot.handlers.admin import is_admin, admin_ids, save_admin_ids
from modern_bot.handlers.common import safe_reply
from modern_bot.handlers.user_management import add_user_by_id, remove_user_by_id, get_all_users

logger = logging.getLogger(__name__)

# Actions (stored in context.user_data['admin_action'])
ACTION_ADD_USER = 'add_user'
ACTION_REMOVE_USER = 'remove_user'
ACTION_ADD_ADMIN = 'add_admin'
ACTION_REMOVE_ADMIN = 'remove_admin'
ACTION_BROADCAST = 'broadcast'

# Interactive handlers
async def prompt_add_user(update: Update, context: CallbackContext):
    """Prompt for user ID to add."""
    query = update.callback_query
    await query.answer()
    
    context.user_data['admin_action'] = ACTION_ADD_USER
    await query.message.reply_text(
        "➕ <b>Добавить пользователя</b>\n\n"
        "Введите ID пользователя:",
        parse_mode="HTML",
        reply_markup=ForceReply(selective=True)
    )

async def prompt_remove_user(update: Update, context: CallbackContext):
    """Prompt for user ID to remove."""
    query = update.callback_query
    await query.answer()
    
    context.user_data['admin_action'] = ACTION_REMOVE_USER
    await query.message.reply_text(
        "➖ <b>Удалить пользователя</b>\n\n"
        "Введите ID пользователя:",
        parse_mode="HTML",
        reply_markup=ForceReply(selective=True)
    )

async def prompt_add_admin(update: Update, context: CallbackContext):
    """Prompt for admin ID to add."""
    query = update.callback_query
    await query.answer()
    
    context.user_data['admin_action'] = ACTION_ADD_ADMIN
    await query.message.reply_text(
        "➕ <b>Добавить администратора</b>\n\n"
        "Введите ID пользователя:",
        parse_mode="HTML",
        reply_markup=ForceReply(selective=True)
    )

async def prompt_remove_admin(update: Update, context: CallbackContext):
    """Prompt for admin ID to remove."""
    query = update.callback_query
    await query.answer()
    
    context.user_data['admin_action'] = ACTION_REMOVE_ADMIN
    await query.message.reply_text(
        "➖ <b>Удалить администратора</b>\n\n"
        "⚠️ Нельзя удалить себя или супер-админов.\n\n"
        "Введите ID администратора:",
        parse_mode="HTML",
        reply_markup=ForceReply(selective=True)
    )

async def prompt_broadcast(update: Update, context: CallbackContext):
    """Prompt for broadcast message."""
    query = update.callback_query
    await query.answer()
    
    context.user_data['admin_action'] = ACTION_BROADCAST
    await query.message.reply_text(
        "📢 <b>Рассылка</b>\n\n"
        "Введите текст сообщения для рассылки всем пользователям:",
        parse_mode="HTML",
        reply_markup=ForceReply(selective=True)
    )

# Main reply handler
async def handle_admin_reply(update: Update, context: CallbackContext):
    """Handle all admin replies based on stored action."""
    requester_id = update.effective_user.id
    
    if not is_admin(requester_id):
        return
    
    action = context.user_data.get('admin_action')
    if not action:
        return
    
    text = update.message.text.strip()
    
    if action == ACTION_ADD_USER:
        try:
            user_id = int(text)
        except ValueError:
            await safe_reply(update, "❌ ID должен быть числом. Попробуйте ещё раз:")
            return
        
        result = await add_user_by_id(user_id, requester_id)
        await safe_reply(update, result)
        context.user_data.pop('admin_action', None)
    
    elif action == ACTION_REMOVE_USER:
        try:
            user_id = int(text)
        except ValueError:
            await safe_reply(update, "❌ ID должен быть числом. Попробуйте ещё раз:")
            return
        
        result = await remove_user_by_id(user_id, requester_id)
        await safe_reply(update, result)
        context.user_data.pop('admin_action', None)
    
    elif action == ACTION_ADD_ADMIN:
        try:
            new_admin_id = int(text)
        except ValueError:
            await safe_reply(update, "❌ ID должен быть числом. Попробуйте ещё раз:")
            return
        
        if new_admin_id in admin_ids:
            await safe_reply(update, "ℹ️ Пользователь уже является администратором.")
        else:
            admin_ids.add(new_admin_id)
            save_admin_ids()
            await safe_reply(update, f"✅ Администратор {new_admin_id} добавлен.")
        
        context.user_data.pop('admin_action', None)
    
    elif action == ACTION_REMOVE_ADMIN:
        try:
            target_id = int(text)
        except ValueError:
            await safe_reply(update, "❌ ID должен быть числом. Попробуйте ещё раз:")
            return
        
        if target_id == requester_id:
            await safe_reply(update, "❌ Нельзя удалить себя из админов.")
        elif target_id not in admin_ids:
            await safe_reply(update, f"ℹ️ Пользователь {target_id} не является администратором.")
        else:
            admin_ids.remove(target_id)
            save_admin_ids()
            await safe_reply(update, f"✅ Администратор {target_id} удалён.")
        
        context.user_data.pop('admin_action', None)
    
    elif action == ACTION_BROADCAST:
        if not text:
            await safe_reply(update, "❌ Сообщение не может быть пустым. Попробуйте ещё раз:")
            return
        
        users = await get_all_users()
        success_count = 0
        fail_count = 0
        
        for user in users:
            try:
                await context.bot.send_message(
                    chat_id=user['user_id'],
                    text=f"📢 <b>Рассылка от администрации:</b>\n\n{text}",
                    parse_mode="HTML"
                )
                success_count += 1
            except Exception as e:
                logger.error(f"Failed to send broadcast to {user['user_id']}: {e}")
                fail_count += 1
        
        await safe_reply(
            update,
            f"✅ Рассылка завершена!\n\n"
            f"Успешно: {success_count}\n"
            f"Ошибок: {fail_count}"
        )
        context.user_data.pop('admin_action', None)

