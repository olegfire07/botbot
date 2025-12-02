import asyncio
import logging
from html import escape as html_escape
from telegram import Update, ForceReply
from telegram.ext import CallbackContext
from telegram.error import RetryAfter, TimedOut, NetworkError, TelegramError
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
        "⚠️ Нельзя удалить себя или Супер-Админа.\n\n"
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
        "Отправьте <b>текст</b> или <b>фотографию</b> (можно с подписью) для рассылки всем пользователям:",
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
    
    # Check for text or caption (if photo)
    text = update.message.text or update.message.caption or ""
    text = text.strip()
    photo = update.message.photo
    
    if action == ACTION_ADD_USER:
        try:
            user_id = int(text)
            if user_id <= 0 or user_id > 100_000_000_000: # Basic sanity check
                raise ValueError("Invalid ID range")
        except ValueError:
            await safe_reply(update, "❌ ID должен быть положительным числом. Попробуйте ещё раз:")
            return
        
        if user_id == requester_id:
             await safe_reply(update, "ℹ️ Вы не можете добавить самого себя (вы уже здесь).")
             return

        result = await add_user_by_id(user_id, requester_id)
        await safe_reply(update, result)
        context.user_data.pop('admin_action', None)
    
    elif action == ACTION_REMOVE_USER:
        try:
            user_id = int(text)
            if user_id <= 0:
                raise ValueError("Invalid ID")
        except ValueError:
            await safe_reply(update, "❌ ID должен быть положительным числом. Попробуйте ещё раз:")
            return
        
        result = await remove_user_by_id(user_id, requester_id)
        await safe_reply(update, result)
        context.user_data.pop('admin_action', None)
    
    elif action == ACTION_ADD_ADMIN:
        try:
            new_admin_id = int(text)
            if new_admin_id <= 0 or new_admin_id > 100_000_000_000:
                raise ValueError("Invalid ID range")
        except ValueError:
            await safe_reply(update, "❌ ID должен быть положительным числом. Попробуйте ещё раз:")
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
            if target_id <= 0:
                raise ValueError("Invalid ID")
        except ValueError:
            await safe_reply(update, "❌ ID должен быть положительным числом. Попробуйте ещё раз:")
            return
        
        if target_id == requester_id:
            await safe_reply(update, "❌ Нельзя удалить себя из админов.")
        elif target_id == 2064900:  # Hardcoded Super Admin check for safety
            await safe_reply(update, "❌ Нельзя удалить Супер-Админа.")
        elif target_id not in admin_ids:
            await safe_reply(update, f"ℹ️ Пользователь {target_id} не является администратором.")
        else:
            admin_ids.remove(target_id)
            save_admin_ids()
            await safe_reply(update, f"✅ Администратор {target_id} удалён.")
        
        context.user_data.pop('admin_action', None)
    
    elif action == ACTION_BROADCAST:
        if not text and not photo:
            await safe_reply(update, "❌ Сообщение не может быть пустым. Отправьте текст или фото.")
            return
            
        # Check limits
        prefix = "📢 <b>Рассылка от администрации:</b>\n\n"
        max_len = 1024 if photo else 4096
        
        if len(text) + len(prefix) > max_len:
            await safe_reply(update, f"❌ Сообщение слишком длинное. Максимум {max_len - len(prefix)} символов.")
            return
        
        users = await get_all_users()
        success_count = 0
        fail_count = 0

        async def send_with_backoff(chat_id: int) -> bool:
            for attempt in range(3):
                try:
                    if photo:
                        # Escape HTML to prevent parse errors
                        safe_text = html_escape(text) if text else None
                        caption_text = f"{prefix}{safe_text}" if safe_text else prefix.rstrip()
                        
                        await context.bot.send_photo(
                            chat_id=chat_id,
                            photo=photo[-1].file_id,
                            caption=caption_text,
                            parse_mode="HTML"
                        )
                    else:
                        # Escape HTML to prevent parse errors
                        safe_text = html_escape(text)
                        await context.bot.send_message(
                            chat_id=chat_id,
                            text=f"{prefix}{safe_text}",
                            parse_mode="HTML"
                        )
                    return True
                except RetryAfter as e:
                    await asyncio.sleep(getattr(e, "retry_after", 1) + 0.5)
                except (TimedOut, NetworkError):
                    await asyncio.sleep(2 ** attempt)
                except TelegramError as e:
                    logger.error(f"Failed to send broadcast to {chat_id}: {e}")
                    return False
                except Exception as e:
                    logger.error(f"Unexpected error sending broadcast to {chat_id}: {e}")
                    return False
            return False

        # Notify admin start
        await safe_reply(update, f"🚀 Начинаю рассылку для {len(users)} пользователей...")

        for user in users:
            if await send_with_backoff(user['user_id']):
                success_count += 1
            else:
                fail_count += 1
            await asyncio.sleep(0.15)  # Increased from 0.05 to avoid Telegram flood limits

        await safe_reply(
            update,
            f"✅ Рассылка завершена!\n\n"
            f"Успешно: {success_count}\n"
            f"Ошибок: {fail_count}"
        )
        context.user_data.pop('admin_action', None)
