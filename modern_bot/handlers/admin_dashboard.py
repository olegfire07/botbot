import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import CallbackContext, CallbackQueryHandler
from modern_bot.handlers.admin import is_admin
from modern_bot.handlers.common import safe_reply
from modern_bot.config import REGION_TOPICS

logger = logging.getLogger(__name__)

async def admin_dashboard_handler(update: Update, context: CallbackContext) -> None:
    """Show admin dashboard with inline buttons."""
    user_id = update.effective_user.id
    
    if not is_admin(user_id):
        await safe_reply(update, "❌ Доступ запрещен.")
        return
    
    # WebApp URL from config
    web_app_url = "https://olegfire07.github.io/botbot/web_app/?v=4.1"
    
    keyboard = [
        [
            InlineKeyboardButton("📝 Создать заключение (Web App)", web_app=WebAppInfo(url=web_app_url))
        ],
        [
            InlineKeyboardButton("💬 Создать через диалог", callback_data="admin_create_dialog")
        ],
        [
            InlineKeyboardButton("📊 Статистика", callback_data="analytics_main"),
            InlineKeyboardButton("📈 Аналитика", callback_data="analytics_regions")
        ],
        [
            InlineKeyboardButton("📦 Архив", callback_data="admin_archive"),
            InlineKeyboardButton("📋 История", callback_data="admin_history")
        ],
        [
            InlineKeyboardButton("👥 Пользователи", callback_data="users_list"),
            InlineKeyboardButton("⚙️ Администраторы", callback_data="admins_list")
        ],
        [
            InlineKeyboardButton("📢 Рассылка", callback_data="admin_broadcast"),
            InlineKeyboardButton("🖥️ Система", callback_data="admin_system")
        ],
        [
            InlineKeyboardButton("🔍 Сверка билетов", callback_data="admin_reconcile"),
            InlineKeyboardButton("🔎 Поиск по билету", callback_data="admin_search_ticket")
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
    elif action == "admin_system":
        await show_system_status(update, context)
    elif action == "admin_download_db":
        await send_database_file(update, context)
    elif action == "admin_restore_db":
        await show_backups_menu(update, context)
    elif action.startswith("restore_backup|"):
        await handle_backup_restore(update, context, action)
    elif action == "admin_download_month":
        await show_download_menu(update, context)
    elif action == "admin_history":
        await show_history(update, context)
    elif action == "admin_users":
        await show_users_menu(update, context)
    elif action == "admin_admins":
        await show_admins_menu(update, context)
    elif action == "admin_broadcast":
        from modern_bot.handlers.admin_interactive import prompt_broadcast
        await query.edit_message_text("📢 Подготовка рассылки...")
        await prompt_broadcast(update, context)
    elif action == "admin_dl_current":
        from datetime import datetime
        month = datetime.now().strftime("%m.%Y")
        await query.answer("Выберите регион…", show_alert=False)
        await show_region_menu(update, context, month)
    elif action == "admin_dl_last":
        from datetime import datetime, timedelta
        last_month = datetime.now().replace(day=1) - timedelta(days=1)
        month = last_month.strftime("%m.%Y")
        await query.answer("Выберите регион…", show_alert=False)
        await show_region_menu(update, context, month)
    elif action.startswith("admin_dl_region|"):
        await handle_region_choice(update, context, action)
    elif action == "admin_create_dialog":
        # Send the /start_chat command to the admin to start dialog mode
        await query.edit_message_text(
            "🗨️ Запускаем диалоговое создание заключения...",
            parse_mode="HTML",
        )
        # Send the command as a message so the ConversationHandler picks it up
        await context.bot.send_message(
            chat_id=update.effective_user.id,
            text="/start_chat"
        )
        # No further processing needed

    elif action == "admin_archive":
        await show_download_menu(update, context)
    
    elif action.startswith("admin_archive_period|"):
        from modern_bot.utils.date_helper import DateFilter
        from modern_bot.handlers.reports import send_period_archive
        from modern_bot.handlers.admin_interactive import prompt_archive_custom_dates
        
        start_date, end_date = DateFilter.process_callback(action)
        
        if start_date and end_date:
            await query.edit_message_text(f"⏳ Формирую архив за {start_date.strftime('%d.%m.%Y')} - {end_date.strftime('%d.%m.%Y')}...")
            await send_period_archive(update, context, start_date, end_date)
        elif "custom" in action:
             await prompt_archive_custom_dates(update, context)
        else:
             # Should not happen if DateFilter works correctly
             await query.answer("Ошибка выбора даты", show_alert=True)


async def show_stats(update: Update, context: CallbackContext) -> None:
    """Show quick stats with back button."""
    from modern_bot.services.excel import read_excel_data
    
    records = await read_excel_data()
    total = len(records)
    
    # Simple stats by region
    regions = {}
    for r in records:
        reg = r[4] if len(r) > 4 else "Неизвестно"  # Region column
        regions[reg] = regions.get(reg, 0) + 1
    
    text = f"📊 <b>Общая статистика</b>\n\nВсего заключений: {total}\n\n<b>По регионам:</b>\n"
    for reg, count in sorted(regions.items(), key=lambda x: x[1], reverse=True):
        text += f"• {reg}: {count}\n"
    
    # Add back button
    keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data="admin_refresh")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.callback_query.edit_message_text(
        text,
        parse_mode="HTML",
        reply_markup=reply_markup
    )

async def show_system_status(update: Update, context: CallbackContext) -> None:
    """Show system status (disk, DB, uptime)."""
    import time
    import shutil
    from modern_bot.config import BASE_DIR, DATABASE_FILE
    from datetime import datetime
    
    # Disk space
    try:
        total, used, free = shutil.disk_usage(BASE_DIR)
        total_gb = total / (1024**3)
        free_gb = free / (1024**3)
        used_percent = (used / total) * 100
        disk_info = f"{free_gb:.1f} GB  / {total_gb:.1f} GB ({used_percent:.0f}% used)"
    except Exception as e:
        logger.warning(f"Failed to get disk usage: {e}")
        disk_info = "N/A"
    
    # Database size
    try:
        db_size_mb = DATABASE_FILE.stat().st_size / (1024**2)
        db_info = f"{db_size_mb:.2f} MB"
    except Exception as e:
        logger.warning(f"Failed to get DB size: {e}")
        db_info = "N/A"
    
    # Uptime (estimate from bot start)
    # Note: This is a rough estimate, actual uptime tracking would need a global variable
    uptime_info = "Running (exact uptime unavailable)"
    
    # Archive stats
    try:
        archive_dir = BASE_DIR / "documents_archive"
        if archive_dir.exists():
            archive_files = sum(1 for f in archive_dir.rglob('*') if f.is_file() and f.name != 'index.json')
        else:
            archive_files = 0
    except Exception as e:
        logger.warning(f"Failed to count archive files: {e}")
        archive_files = 0
    
    # Backup stats  
    try:
        backups_dir = BASE_DIR / "backups"
        if backups_dir.exists():
            backup_files = sum(1 for f in backups_dir.iterdir() if f.is_file())
        else:
            backup_files = 0
    except Exception as e:
        logger.warning(f"Failed to count backup files: {e}")
        backup_files = 0
    
    text = (
        f"🖥️ <b>Состояние системы</b>\n\n"
        f"💾 <b>Диск:</b> {disk_info}\n"
        f"🗄 <b>База данных:</b> {db_info}\n"
        f"⏱ <b>Uptime:</b> {uptime_info}\n\n"
        f"📦 <b>Архив:</b> {archive_files} файлов\n"
        f"💾 <b>Бэкапы:</b> {backup_files} файлов"
    )
    
    keyboard = [
        [InlineKeyboardButton("💾 Скачать БД", callback_data="admin_download_db")],
        [InlineKeyboardButton("♻️ Восстановить из бэкапа", callback_data="admin_restore_db")],
        [InlineKeyboardButton("◀️ Назад", callback_data="admin_refresh")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.callback_query.edit_message_text(
        text,
        parse_mode="HTML",
        reply_markup=reply_markup
    )

async def send_database_file(update: Update, context: CallbackContext) -> None:
    """Send database file to admin."""
    from modern_bot.config import DATABASE_FILE
    from datetime import datetime
    import os
    
    if not DATABASE_FILE.exists():
        await update.callback_query.answer("❌ Файл базы данных не найден!", show_alert=True)
        return
    
    await update.callback_query.answer("📤 Отправляю базу данных...")
    
    try:
        # Send database file
        with open(DATABASE_FILE, 'rb') as db_file:
            await update.callback_query.message.reply_document(
                document=db_file,
                filename=f"user_data_{datetime.now().strftime('%Y-%m-%d_%H-%M')}.db",
                caption=f"💾 <b>База данных</b>\n\n"
                f"📊 Размер: {os.path.getsize(DATABASE_FILE) / 1024:.1f} KB\n"
                f"🕐 Время: {datetime.now().strftime('%d.%m.%Y %H:%M')}",
                parse_mode="HTML"
            )
        logger.info(f"Database sent to admin {update.effective_user.id}")
    except Exception as e:
        logger.error(f"Failed to send database: {e}")
        await update.callback_query.message.reply_text(
            f"❌ Ошибка при отправке базы данных: {e}"
        )

from modern_bot.handlers.backup_restore import show_backups_menu, handle_backup_restore

async def show_analytics(update: Update, context: CallbackContext) -> None:
    """Show analytics menu."""
    keyboard = [
        [InlineKeyboardButton("📊 По регионам", callback_data="analytics_regions")],
        [InlineKeyboardButton("📈 По подразделениям", callback_data="analytics_departments")],
        [InlineKeyboardButton("👥 Топ пользователей", callback_data="analytics_top_users")],
        [InlineKeyboardButton("📅 По дням", callback_data="analytics_daily")],
        [InlineKeyboardButton("🗓 За период", callback_data="analytics_select_period")],
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
    from modern_bot.utils.date_helper import DateFilter
    from modern_bot.handlers.admin_interactive import prompt_analytics_custom_dates
    
    query = update.callback_query
    await query.answer()
    
    action = query.data
    
    keyboard = [[InlineKeyboardButton("◀️ Назад к аналитике", callback_data="admin_analytics")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if action == "analytics_main":
        await show_analytics(update, context)
        return

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
        
    elif action == "analytics_select_period":
        # Show DateFilter keyboard
        keyboard = DateFilter.get_keyboard("analytics_period")
        keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="analytics_main")])
        await query.edit_message_text(
            "📅 <b>Выберите период для аналитики:</b>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
    elif action.startswith("analytics_period|"):
        start_date, end_date = DateFilter.process_callback(action)
        
        if start_date and end_date:
            await query.edit_message_text(f"⏳ Считаю статистику за {start_date.strftime('%d.%m.%Y')} - {end_date.strftime('%d.%m.%Y')}...")
            stats = await AnalyticsService.get_period_stats(start_date, end_date)
            report = AnalyticsService.format_period_report(stats, start_date, end_date)
            await query.edit_message_text(report, parse_mode="HTML", reply_markup=reply_markup)
        elif "custom" in action:
             await prompt_analytics_custom_dates(update, context)
        else:
             await query.answer("Ошибка выбора даты", show_alert=True)

async def show_download_menu(update: Update, context: CallbackContext) -> None:
    """Show download month instruction."""
    from modern_bot.utils.date_helper import DateFilter
    
    keyboard = DateFilter.get_keyboard("admin_archive_period")
    keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="admin_refresh")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.callback_query.edit_message_text(
        "📦 <b>Скачать архив</b>\n\n"
        "Выберите период или используйте команду:\n"
        "<code>/download_month ММ.ГГГГ [Регион]</code>",
        parse_mode="HTML",
        reply_markup=reply_markup
    )

async def show_region_menu(update: Update, context: CallbackContext, month: str) -> None:
    """Ask admin to choose region for the archive."""
    try:
        regions = list(REGION_TOPICS.keys())
        context.user_data["dl_regions"] = regions
        context.user_data["dl_month"] = month

        keyboard = [[InlineKeyboardButton("🌍 Все регионы", callback_data=f"admin_dl_region|{month}|all")]]
        for idx, region in enumerate(regions):
            keyboard.append([InlineKeyboardButton(region, callback_data=f"admin_dl_region|{month}|{idx}")])
        keyboard.append([InlineKeyboardButton("◀️ Назад к выбору месяца", callback_data="admin_download_month")])

        target_message = update.callback_query.message if update.callback_query else update.effective_message
        if target_message:
            await target_message.edit_text(
                f"📦 <b>Архив за {month}</b>\n\nВыберите регион:",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        else:
            await safe_reply(update, "Не удалось показать выбор региона.")
    except Exception as e:
        await safe_reply(update, f"Ошибка при показе регионов: {e}")

async def handle_region_choice(update: Update, context: CallbackContext, action: str) -> None:
    """Handle region selection for month archive."""
    parts = action.split("|", 2)
    if len(parts) != 3:
        await safe_reply(update, "Неверный формат запроса архива.")
        return
    _, month, region_key = parts
    regions = context.user_data.get("dl_regions", list(REGION_TOPICS.keys()))
    region = None
    if region_key != "all":
        try:
            idx = int(region_key)
            region = regions[idx]
        except (ValueError, IndexError):
            await safe_reply(update, "Не удалось определить регион.")
            return

    from modern_bot.handlers.reports import send_month_archive
    await send_month_archive(update, context, month, region)

async def show_history(update: Update, context: CallbackContext) -> None:
    """Show history with back button."""
    from modern_bot.services.excel import read_excel_data
    from modern_bot.utils.formatters import format_history_list
    
    records = await read_excel_data()
    text = format_history_list(records)
    
    keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data="admin_refresh")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.callback_query.edit_message_text(
        text,
        parse_mode="HTML",
        reply_markup=reply_markup
    )




def get_admin_callback_handler():
    """Returns a CallbackQueryHandler that manages all admin actions."""
    # Pattern excludes admin_reconcile and admin_search_ticket which have dedicated ConversationHandlers
    return CallbackQueryHandler(
        handle_all_callbacks,
        pattern=r"^(?!admin_reconcile$|admin_search_ticket$)(admin_|analytics_|users_|admins_|broadcast_)"
    )

async def handle_all_callbacks(update: Update, context: CallbackContext) -> None:
    """Route all admin and analytics callbacks."""
    # Reset DB upload flag to prevent stuck state
    context.user_data['awaiting_db_upload'] = False
    
    action = update.callback_query.data
    
    if action.startswith("analytics_"):
        await analytics_callback_handler(update, context)
    elif action.startswith("users_"):
        await users_management_callback_handler(update, context)
    elif action.startswith("admins_"):
        await admins_management_callback_handler(update, context)
    elif action.startswith("broadcast_"):
        await broadcast_callback_handler(update, context)
    elif action.startswith("admin_"):
        await admin_callback_handler(update, context)


# User Management Section
async def show_users_menu(update: Update, context: CallbackContext) -> None:
    """Show users management menu."""
    keyboard = [
        [InlineKeyboardButton("➕ Добавить пользователя", callback_data="users_add")],
        [InlineKeyboardButton("➖ Удалить пользователя", callback_data="users_remove")],
        [InlineKeyboardButton("📋 Список пользователей", callback_data="users_list")],
        [InlineKeyboardButton("◀️ Назад", callback_data="admin_refresh")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.callback_query.edit_message_text(
        "👥 <b>Управление пользователями</b>\n\n"
        "Выберите действие:",
        parse_mode="HTML",
        reply_markup=reply_markup
    )

async def show_admins_menu(update: Update, context: CallbackContext) -> None:
    """Show admins management menu."""
    from modern_bot.handlers.admin import admin_ids
    
    admin_list = "\n".join([f"• <code>{aid}</code>" for aid in sorted(admin_ids)])
    
    keyboard = [
        [InlineKeyboardButton("➕ Добавить админа", callback_data="admins_add")],
        [InlineKeyboardButton("➖ Удалить админа", callback_data="admins_remove")],
        [InlineKeyboardButton("🔄 Обновить список", callback_data="admins_refresh")],
        [InlineKeyboardButton("◀️ Назад", callback_data="admin_refresh")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    text = (
        f"⚙️ <b>Управление администраторами</b>\n\n"
        f"<b>Текущие админы ({len(admin_ids)}):</b>\n{admin_list}\n\n"
        f"Выберите действие:"
    )
    
    await update.callback_query.edit_message_text(
        text,
        parse_mode="HTML",
        reply_markup=reply_markup
    )

async def users_management_callback_handler(update: Update, context: CallbackContext) -> None:
    """Handle users management callbacks."""
    from modern_bot.handlers.user_management import list_users_handler
    
    query = update.callback_query
    await query.answer()
    
    action = query.data
    
    if action == "users_list":
        text = await list_users_handler(update, context)
        keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data="admin_users")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=reply_markup)
    
    elif action == "users_add":
        from modern_bot.handlers.admin_interactive import prompt_add_user
        await query.edit_message_text("➕ Добавление пользователя...")
        await prompt_add_user(update, context)
    
    elif action == "users_remove":
        from modern_bot.handlers.admin_interactive import prompt_remove_user
        await query.edit_message_text("➖ Удаление пользователя...")
        await prompt_remove_user(update, context)

async def admins_management_callback_handler(update: Update, context: CallbackContext) -> None:
    """Handle admins management callbacks."""
    query = update.callback_query
    await query.answer()
    
    action = query.data
    
    if action == "admins_list" or action == "admins_refresh":
        await show_admins_menu(update, context)
    
    elif action == "admins_add":
        from modern_bot.handlers.admin_interactive import prompt_add_admin
        await query.edit_message_text("➕ Добавление администратора...")
        await prompt_add_admin(update, context)
    
    elif action == "admins_remove":
        from modern_bot.handlers.admin_interactive import prompt_remove_admin
        await query.edit_message_text("➖ Удаление администратора...")
        await prompt_remove_admin(update, context)

async def broadcast_callback_handler(update: Update, context: CallbackContext) -> None:
    """Handle broadcast callbacks."""
    from modern_bot.handlers.admin_interactive import prompt_broadcast_content, prompt_broadcast_region
    
    query = update.callback_query
    await query.answer()
    
    action = query.data
    
    if action == "broadcast_all":
        await prompt_broadcast_content(update, context, region=None)
        
    elif action == "broadcast_region":
        await prompt_broadcast_region(update, context)
        
    elif action.startswith("broadcast_target|"):
        _, region = action.split("|", 1)
        await prompt_broadcast_content(update, context, region=region)
