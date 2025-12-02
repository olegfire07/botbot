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
ACTION_ARCHIVE_CUSTOM = 'archive_custom'
ACTION_ANALYTICS_CUSTOM = 'analytics_custom'

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

async def prompt_archive_custom_dates(update: Update, context: CallbackContext):
    """Prompt for custom dates for archive."""
    query = update.callback_query
    await query.answer()
    
    context.user_data['admin_action'] = ACTION_ARCHIVE_CUSTOM
    await query.message.reply_text(
        "📦 <b>Архив за период</b>\n\n"
        "Введите даты в формате: ДД.ММ.ГГГГ - ДД.ММ.ГГГГ\n"
        "Пример: <code>01.11.2025 - 15.11.2025</code>",
        parse_mode="HTML",
        reply_markup=ForceReply(selective=True)
    )

async def prompt_analytics_custom_dates(update: Update, context: CallbackContext):
    """Prompt for custom dates for analytics."""
    query = update.callback_query
    await query.answer()
    
    context.user_data['admin_action'] = ACTION_ANALYTICS_CUSTOM
    await query.message.reply_text(
        "📈 <b>Аналитика за период</b>\n\n"
        "Введите даты в формате: ДД.ММ.ГГГГ - ДД.ММ.ГГГГ\n"
        "Пример: <code>01.11.2025 - 15.11.2025</code>",
        parse_mode="HTML",
        reply_markup=ForceReply(selective=True)
    )

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from modern_bot.config import REGION_TOPICS

async def prompt_broadcast(update: Update, context: CallbackContext):
    """Prompt for broadcast type."""
    keyboard = [
        [InlineKeyboardButton("📢 Всем пользователям", callback_data="broadcast_all")],
        [InlineKeyboardButton("🌍 По региону", callback_data="broadcast_region")],
        [InlineKeyboardButton("◀️ Отмена", callback_data="admin_refresh")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # If called from callback
    if update.callback_query:
        await update.callback_query.edit_message_text(
            "📢 <b>Рассылка</b>\n\nВыберите получателей:",
            parse_mode="HTML",
            reply_markup=reply_markup
        )
    else:
        await update.message.reply_text(
            "📢 <b>Рассылка</b>\n\nВыберите получателей:",
            parse_mode="HTML",
            reply_markup=reply_markup
        )

async def prompt_broadcast_region(update: Update, context: CallbackContext):
    """Show region selection for broadcast."""
    query = update.callback_query
    await query.answer()
    
    keyboard = []
    regions = list(REGION_TOPICS.keys())
    
    # Group regions by 2
    for i in range(0, len(regions), 2):
        row = [InlineKeyboardButton(regions[i], callback_data=f"broadcast_target|{regions[i]}")]
        if i + 1 < len(regions):
            row.append(InlineKeyboardButton(regions[i+1], callback_data=f"broadcast_target|{regions[i+1]}"))
        keyboard.append(row)
        
    keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="admin_broadcast")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "🌍 <b>Выберите регион для рассылки:</b>",
        parse_mode="HTML",
        reply_markup=reply_markup
    )

async def prompt_broadcast_content(update: Update, context: CallbackContext, region: str = None):
    """Ask for content."""
    query = update.callback_query
    await query.answer()
    
    context.user_data['admin_action'] = ACTION_BROADCAST
    context.user_data['broadcast_region'] = region
    
    target_text = f"региону <b>{region}</b>" if region else "<b>всем пользователям</b>"
    
    await query.message.reply_text(
        f"📢 <b>Рассылка по {target_text}</b>\n\n"
        "Отправьте <b>текст</b> или <b>фотографию</b> (можно с подписью) для отправки:",
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

    elif action == ACTION_ARCHIVE_CUSTOM:
        from modern_bot.utils.date_helper import DateFilter
        from modern_bot.handlers.reports import send_period_archive
        
        start_date, end_date = DateFilter.parse_custom_range(text)
        if not start_date:
            await safe_reply(update, "❌ Неверный формат даты. Используйте ДД.ММ.ГГГГ - ДД.ММ.ГГГГ")
            return
            
        await safe_reply(update, f"⏳ Формирую архив за {text}...")
        await send_period_archive(update, context, start_date, end_date)
        context.user_data.pop('admin_action', None)

    elif action == ACTION_ANALYTICS_CUSTOM:
        from modern_bot.utils.date_helper import DateFilter
        from modern_bot.services.analytics import AnalyticsService
        
        start_date, end_date = DateFilter.parse_custom_range(text)
        if not start_date:
            await safe_reply(update, "❌ Неверный формат даты. Используйте ДД.ММ.ГГГГ - ДД.ММ.ГГГГ")
            return
            
        await safe_reply(update, f"⏳ Считаю статистику за {text}...")
        stats = await AnalyticsService.get_period_stats(start_date, end_date)
        report = AnalyticsService.format_period_report(stats, start_date, end_date)
        
        keyboard = [[InlineKeyboardButton("◀️ Назад к аналитике", callback_data="admin_analytics")]]
        await safe_reply(update, report, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))
        context.user_data.pop('admin_action', None)
    
    elif action == ACTION_BROADCAST:
        if not text and not photo:
            await safe_reply(update, "❌ Сообщение не может быть пустым. Отправьте текст или фото.")
            return
            
        # Check limits
        target_region = context.user_data.get('broadcast_region')
        prefix = f"📢 <b>Рассылка ({target_region if target_region else 'Всем'}):</b>\n\n"
        max_len = 1024 if photo else 4096
        
        if len(text) + len(prefix) > max_len:
            await safe_reply(update, f"❌ Сообщение слишком длинное. Максимум {max_len - len(prefix)} символов.")
            return
        
        # Get users
        all_users = await get_all_users()
        users_to_send = []
        
        if target_region:
            # Filter by region
            from modern_bot.database.db import get_db
            db = get_db()
            if db:
                try:
                    async with db.execute(
                        "SELECT user_id FROM user_data WHERE region = ?", 
                        (target_region,)
                    ) as cursor:
                        rows = await cursor.fetchall()
                        target_ids = {row[0] for row in rows}
                        users_to_send = [u for u in all_users if u['user_id'] in target_ids]
                except Exception as e:
                    logger.error(f"Error filtering users by region: {e}")
                    await safe_reply(update, "❌ Ошибка при фильтрации пользователей.")
                    return
            else:
                 await safe_reply(update, "❌ Ошибка БД.")
                 return
        else:
            users_to_send = all_users
            
        if not users_to_send:
            await safe_reply(update, f"❌ Нет пользователей для рассылки (Регион: {target_region or 'Все'}).")
            context.user_data.pop('admin_action', None)
            return

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
        await safe_reply(update, f"🚀 Начинаю рассылку для {len(users_to_send)} пользователей...")

        for user in users_to_send:
            if await send_with_backoff(user['user_id']):
                success_count += 1
            else:
                fail_count += 1
            await asyncio.sleep(0.15)  # Increased from 0.05 to avoid Telegram flood limits

        await safe_reply(
            update,
            f"✅ Рассылка завершена!\n\n"
            f"🎯 Цель: {target_region or 'Все'}\n"
            f"Успешно: {success_count}\n"
            f"Ошибок: {fail_count}"
        )
        context.user_data.pop('admin_action', None)
        context.user_data.pop('broadcast_region', None)
