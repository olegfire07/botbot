import asyncio
import logging
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
    context.user_data['broadcast_photo'] = None
    context.user_data['broadcast_text'] = None
    
    await query.message.reply_text(
        "📢 <b>Рассылка</b>\n\n"
        "Вы можете отправить:\n"
        "• 📸 Фото (одно)\n"
        "• 📝 Текст\n"
        "• 📸 + 📝 Фото с текстом\n\n"
        "После того как отправите контент, используйте команду:\n"
        "<code>/send</code> - для запуска рассылки\n"
        "<code>/cancel</code> - для отмены",
        parse_mode="HTML"
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
        # Handle photo if present
        if update.message.photo:
            photo = update.message.photo[-1]  # Get highest quality
            context.user_data['broadcast_photo'] = photo.file_id
            
            # Check if there's a caption
            if update.message.caption:
                caption = update.message.caption.strip()
                if len(caption) > 1024:
                    await safe_reply(update, f"❌ Подпись слишком длинная ({len(caption)} символов). Максимум 1024 для фото.")
                    return
                context.user_data['broadcast_text'] = caption
            
            await safe_reply(
                update,
                "✅ Фото получено!\n\n"
                "Отправьте команду:\n"
                "• <code>/send</code> - отправить рассылку\n"
                "• Или добавьте/измените текст\n"
                "• <code>/cancel</code> - отменить",
                parse_mode="HTML"
            )
            return
        
        # Handle commands
        if text.startswith('/'):
            if text == '/send':
                # Execute broadcast
                photo_id = context.user_data.get('broadcast_photo')
                broadcast_text = context.user_data.get('broadcast_text', '')
                
                # Validation
                if not photo_id and not broadcast_text:
                    await safe_reply(update, "❌ Нужно отправить хотя бы фото или текст!")
                    return
                
                if broadcast_text and len(broadcast_text) > (1024 if photo_id else 4000):
                    max_len = 1024 if photo_id else 4000
                    await safe_reply(update, f"❌ Текст слишком длинный ({len(broadcast_text)} символов). Максимум {max_len}.")
                    return
                
                # Get users and send broadcast
                users = await get_all_users()
                success_count = 0
                fail_count = 0

                async def send_with_backoff(chat_id: int) -> bool:
                    for attempt in range(3):
                        try:
                            if photo_id:
                                # Send photo with or without caption
                                caption = f"📢 <b>Рассылка от администрации:</b>\n\n{broadcast_text}" if broadcast_text else "📢 <b>Рассылка от администрации</b>"
                                await context.bot.send_photo(
                                    chat_id=chat_id,
                                    photo=photo_id,
                                    caption=caption,
                                    parse_mode="HTML"
                                )
                            else:
                                # Send text only
                                await context.bot.send_message(
                                    chat_id=chat_id,
                                    text=f"📢 <b>Рассылка от администрации:</b>\n\n{broadcast_text}",
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

                for user in users:
                    if await send_with_backoff(user['user_id']):
                        success_count += 1
                    else:
                        fail_count += 1
                    await asyncio.sleep(0.05)  # throttle to reduce flood risks

                await safe_reply(
                    update,
                    f"✅ Рассылка завершена!\n\n"
                    f"Успешно: {success_count}\n"
                    f"Ошибок: {fail_count}"
                )
                
                # Cleanup
                context.user_data.pop('admin_action', None)
                context.user_data.pop('broadcast_photo', None)
                context.user_data.pop('broadcast_text', None)
                
            elif text == '/cancel':
                context.user_data.pop('admin_action', None)
                context.user_data.pop('broadcast_photo', None)
                context.user_data.pop('broadcast_text', None)
                await safe_reply(update, "❌ Рассылка отменена.")
            else:
                await safe_reply(update, "❓ Неизвестная команда. Используйте /send или /cancel")
            return
        
        # Handle text message
        if not text:
            await safe_reply(update, "❌ Сообщение не может быть пустым.")
            return
        
        # Check text length based on whether photo is present
        photo_id = context.user_data.get('broadcast_photo')
        max_length = 1024 if photo_id else 4000
        
        if len(text) > max_length:
            await safe_reply(update, f"❌ Текст слишком длинный ({len(text)} символов). Максимум {max_length}.")
            return
        
        context.user_data['broadcast_text'] = text
        
        status = "✅ Текст получен!\n\n"
        if photo_id:
            status += "📸 Фото: Да\n📝 Текст: Да\n\n"
        else:
            status += "📝 Текст: Да\n\n"
        
        status += "Отправьте команду:\n• <code>/send</code> - отправить рассылку\n• <code>/cancel</code> - отменить"
        
        await safe_reply(update, status, parse_mode="HTML")
