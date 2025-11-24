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
    elif action == "admin_dl_current":
        from datetime import datetime
        month = datetime.now().strftime("%m.%Y")
        from modern_bot.handlers.reports import send_month_archive
        await send_month_archive(update.callback_query.message, context, month)
    elif action == "admin_dl_last":
        from datetime import datetime, timedelta
        last_month = datetime.now().replace(day=1) - timedelta(days=1)
        month = last_month.strftime("%m.%Y")
        from modern_bot.handlers.reports import send_month_archive
        await send_month_archive(update.callback_query.message, context, month)

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
        [InlineKeyboardButton("📅 По дням", callback_data="analytics_daily")],
        [InlineKeyboardButton("◀️ Назад", callback_data="admin_refresh")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.callback_query.edit_message_text(
        "📈 <b>Аналитика</b>\n\nВыберите тип отчета:",
        parse_mode="HTML",
        reply_markup=reply_markup
    )

async def analytics_callback_handler(update: Update, context: CallbackContext) -> None:
    """Handle analytics callbacks."""
    from modern_bot.services.analytics import AnalyticsService
    
    query = update.callback_query
    await query.answer()
    
    action = query.data
    
    keyboard = [[InlineKeyboardButton("◀️ Назад к аналитике", callback_data="admin_analytics")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if action == "analytics_regions":
        stats = await AnalyticsService.get_region_stats()
        report = AnalyticsService.format_region_report(stats)
        await query.edit_message_text(report, parse_mode="HTML", reply_markup=reply_markup)
    
    elif action == "analytics_departments":
        stats = await AnalyticsService.get_department_stats()
        report = AnalyticsService.format_department_report(stats)
        await query.edit_message_text(report, parse_mode="HTML", reply_markup=reply_markup)
    
    elif action == "analytics_top_users":
        users = await AnalyticsService.get_top_users()
        report = AnalyticsService.format_top_users_report(users)
        await query.edit_message_text(report, parse_mode="HTML", reply_markup=reply_markup)
    
    elif action == "analytics_daily":
        stats = await AnalyticsService.get_daily_stats()
        chart = AnalyticsService.create_simple_chart(stats)
        text = f"📅 <b>Документы по дням (последние 30 дней)</b>\n\n{chart}"
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=reply_markup)

async def show_download_menu(update: Update, context: CallbackContext) -> None:
    """Show download month instruction."""
    from datetime import datetime, timedelta
    now = datetime.now()
    curr_month = now.strftime("%m.%Y")
    last_month = (now.replace(day=1) - timedelta(days=1)).strftime("%m.%Y")

    keyboard = [
        [InlineKeyboardButton(f"📅 Текущий ({curr_month})", callback_data="admin_dl_current")],
        [InlineKeyboardButton(f"📅 Прошлый ({last_month})", callback_data="admin_dl_last")],
        [InlineKeyboardButton("◀️ Назад", callback_data="admin_refresh")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.callback_query.edit_message_text(
        "📦 <b>Скачать архив за месяц</b>\n\n"
        "Выберите месяц или используйте команду:\n"
        "<code>/download_month ММ.ГГГГ [Регион]</code>",
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
    from telegram.ext import CallbackQueryHandler
    return CallbackQueryHandler(handle_all_callbacks, pattern="^(admin_|analytics_)")

async def handle_all_callbacks(update: Update, context: CallbackContext) -> None:
    """Route all admin and analytics callbacks."""
    action = update.callback_query.data
    
    if action.startswith("analytics_"):
        await analytics_callback_handler(update, context)
    elif action.startswith("admin_"):
        await admin_callback_handler(update, context)
