import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext, CallbackQueryHandler
from modern_bot.handlers.admin import is_admin
from modern_bot.handlers.common import safe_reply

logger = logging.getLogger(__name__)

async def admin_dashboard_handler(update: Update, context: CallbackContext) -> None:
    """Show admin dashboard with inline buttons."""
    user_id = update.effective_user.id
    
    if not is_admin(user_id):
        await safe_reply(update, "❌ Доступ запрещен.")
        return
    
    keyboard = [
        [
            InlineKeyboardButton("📊 Статистика", callback_data="admin_stats"),
            InlineKeyboardButton("📈 Аналитика", callback_data="admin_analytics")
        ],
        [
            InlineKeyboardButton("📦 Архив за месяц", callback_data="admin_download_month"),
            InlineKeyboardButton("📋 История", callback_data="admin_history")
        ],
        [
            InlineKeyboardButton("👥 Добавить админа", callback_data="admin_add_admin"),
            InlineKeyboardButton("📢 Рассылка", callback_data="admin_broadcast")
        ],
        [
            InlineKeyboardButton("🔄 Обновить", callback_data="admin_refresh")
        ]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    text = (
        "🎛 <b>Панель администратора</b>\n\n"
        "Выберите действие:"
    )
    
    if update.callback_query:
        await update.callback_query.edit_message_text(
            text=text,
            parse_mode="HTML",
            reply_markup=reply_markup
        )
    else:
        await update.message.reply_text(
            text=text,
            parse_mode="HTML",
            reply_markup=reply_markup
        )

async def admin_callback_handler(update: Update, context: CallbackContext) -> None:
    """Handle admin dashboard callbacks."""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await query.edit_message_text("❌ Доступ запрещен.")
        return
    
    action = query.data
    
    if action == "admin_refresh":
        await admin_dashboard_handler(update, context)
        return
    
    if action == "admin_stats":
        await show_stats(update, context)
    elif action == "admin_analytics":
        await show_analytics(update, context)
    elif action == "admin_download_month":
        await show_download_menu(update, context)
    elif action == "admin_history":
        await show_history(update, context)
    elif action == "admin_add_admin":
        await query.edit_message_text(
            "👥 Для добавления администратора используйте:\n"
            "<code>/add_admin USER_ID</code>",
            parse_mode="HTML"
        )
    elif action == "admin_broadcast":
        await query.edit_message_text(
            "📢 Для рассылки используйте:\n"
            "<code>/broadcast Ваше сообщение</code>",
            parse_mode="HTML"
        )

async def show_stats(update: Update, context: CallbackContext) -> None:
    """Show quick stats with back button."""
    from modern_bot.handlers.reports import stats_handler
    
    # Call existing stats handler
    await stats_handler(update, context)
    
    # Add back button
    keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data="admin_refresh")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.callback_query.message.reply_text(
        "⬆️ Статистика выше",
        reply_markup=reply_markup
    )

async def show_analytics(update: Update, context: CallbackContext) -> None:
    """Show analytics menu."""
    keyboard = [
        [InlineKeyboardButton("📊 По регионам", callback_data="analytics_regions")],
        [InlineKeyboardButton("📈 По подразделениям", callback_data="analytics_departments")],
        [InlineKeyboardButton("👥 Топ пользователей", callback_data="analytics_top_users")],
        [InlineKeyboardButton("◀️ Назад", callback_data="admin_refresh")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.callback_query.edit_message_text(
        "📈 <b>Аналитика</b>\n\nВыберите тип отчета:",
        parse_mode="HTML",
        reply_markup=reply_markup
    )

async def show_download_menu(update: Update, context: CallbackContext) -> None:
    """Show download month instruction."""
    keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data="admin_refresh")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.callback_query.edit_message_text(
        "📦 <b>Скачать архив за месяц</b>\n\n"
        "Используйте команду:\n"
        "<code>/download_month ММ.ГГГГ [Регион]</code>\n\n"
        "Пример:\n"
        "<code>/download_month 11.2025</code>\n"
        "<code>/download_month 11.2025 Москва</code>",
        parse_mode="HTML",
        reply_markup=reply_markup
    )

async def show_history(update: Update, context: CallbackContext) -> None:
    """Show history with back button."""
    from modern_bot.handlers.reports import history_handler
    
    await history_handler(update, context)
    
    keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data="admin_refresh")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.callback_query.message.reply_text(
        "⬆️ История выше",
        reply_markup=reply_markup
    )

def get_admin_callback_handler():
    """Return callback query handler for admin dashboard."""
    return CallbackQueryHandler(admin_callback_handler, pattern="^admin_")
