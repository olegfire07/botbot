import logging
import os
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
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
    
    from modern_bot.database.db import get_setting
    v = os.getenv("WEB_APP_VERSION", "5.2")
    cv = await get_setting('cache_version', '1')

    base_url = os.getenv("WEB_APP_URL", "https://olegfire07.github.io/BestBOT/").strip()
    url_parts = urlsplit(base_url)
    query = dict(parse_qsl(url_parts.query, keep_blank_values=True))
    query["v"] = v
    query["cv"] = cv

    bot_url_raw = os.getenv('BOT_URL', '').strip()
    bot_host = bot_url_raw or '127.0.0.1:8080'
    if bot_host == 'localhost:8080':
        bot_host = '127.0.0.1:8080'
    if not bot_host.startswith(('http://', 'https://')):
        bot_host_display = f"http://{bot_host}"
    else:
        bot_host_display = bot_host
    bot_host_display = bot_host_display.rstrip('/')

    if bot_url_raw:
        query["bot_url"] = bot_host_display

    web_app_url = urlunsplit(
        (url_parts.scheme, url_parts.netloc, url_parts.path, urlencode(query), url_parts.fragment)
    )
    
    is_super = (user_id == 2064900)
    
    keyboard = [
        [
            InlineKeyboardButton("📝 Новое заключение", web_app=WebAppInfo(url=web_app_url), style='primary')
        ],
        [
            InlineKeyboardButton("🗨️ Создать через бот", callback_data="admin_create_dialog", style='primary')
        ],
        [
            InlineKeyboardButton("🏆 Мой личный рейтинг", callback_data="admin_my_rank", style='primary')
        ],
        [
            InlineKeyboardButton("📊 Статистика", callback_data="analytics_main", style='primary'),
            InlineKeyboardButton("📈 Аналитика", callback_data="analytics_regions", style='primary')
        ],
        [
            InlineKeyboardButton("📦 Архив", callback_data="admin_archive", style='primary'),
            InlineKeyboardButton("📋 История", callback_data="admin_history", style='primary')
        ],
        [
            InlineKeyboardButton("👥 Пользователи", callback_data="users_list", style='primary'),
            InlineKeyboardButton("⚙️ Администраторы", callback_data="admins_list", style='primary')
        ],
        [
            InlineKeyboardButton("📢 Рассылка", callback_data="admin_broadcast", style='primary'),
            InlineKeyboardButton("🖥️ Система", callback_data="admin_system", style='primary')
        ],
        [
            InlineKeyboardButton("🔍 Сверка билетов", callback_data="admin_reconcile", style='primary'),
            InlineKeyboardButton("🔎 Поиск по билету", callback_data="admin_search_ticket", style='primary')
        ],
        [
            InlineKeyboardButton("🔄 Обновить панель", callback_data="admin_refresh", style='primary')
        ]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if is_super:
        text = (
            "👑 *Панель управления BestBOT*\n\n"
            f"🧩 Версия: `{v}` | Кэш: `{cv}`\n\n"
            "🖥️ *Админ-панель (только ПК):*\n"
            f"`{bot_host_display}/super-admin`\n\n"
            "Откройте эту ссылку в браузере на компьютере."
        )
    else:
        text = (
            "⚙️ *Панель администратора*\n\n"
            "Используйте кнопки ниже для управления."
        )
    
    if update.callback_query and update.callback_query.message:
        try:
            await update.callback_query.edit_message_text(
                text,
                reply_markup=reply_markup,
                parse_mode="Markdown"
            )
            return
        except Exception as e:
            logger.warning(f"Failed to edit admin panel message: {e}")

    from modern_bot.handlers.common import safe_reply
    await safe_reply(update, text, reply_markup=reply_markup, parse_mode="Markdown")

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
    
    if action == "admin_my_rank":
        from modern_bot.services.gamification import my_stats_command
        await my_stats_command(update, context)
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
    elif action == "admin_stats_reset":
        from modern_bot.config import SUPER_ADMIN_ID
        if user_id != SUPER_ADMIN_ID:
            await query.edit_message_text("❌ Только супер-админ может сбросить статистику.")
            return
        from modern_bot.services.retention import set_stats_reset_now
        ts = await set_stats_reset_now()
        keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data="admin_system", style='primary')]]
        await query.edit_message_text(
            f"✅ Статистика сброшена (мягко).\n"
            f"Новый отсчет: {ts}",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
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
    elif action.startswith("admin_archive_region|"):
        await handle_period_region_choice(update, context, action)
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
        from modern_bot.handlers.admin_interactive import prompt_archive_custom_dates
        
        start_date, end_date = DateFilter.process_callback(action)
        
        if start_date and end_date:
            period_label = f"{start_date.strftime('%d.%m.%Y')} - {end_date.strftime('%d.%m.%Y')}"
            await show_period_region_menu(update, context, start_date, end_date, period_label)
        elif "custom" in action:
             await prompt_archive_custom_dates(update, context)
        else:
             # Should not happen if DateFilter works correctly
             await query.answer("Ошибка выбора даты", show_alert=True)


async def show_stats(update: Update, context: CallbackContext) -> None:
    """Show quick stats with back button."""
    from modern_bot.services.excel import read_excel_data
    from modern_bot.services.retention import get_effective_cutoff
    from modern_bot.config import DATA_RETENTION_DAYS
    from modern_bot.utils.validators import parse_date_str
    from datetime import datetime
    
    records = await read_excel_data()
    cutoff = await get_effective_cutoff()
    def _row_dt(value):
        if isinstance(value, datetime):
            return value
        return parse_date_str(str(value))

    filtered = [
        r for r in records
        if len(r) > 3 and r[3] and _row_dt(r[3]) and _row_dt(r[3]) >= cutoff
    ]
    total = len(filtered)
    
    # Simple stats by region
    regions = {}
    for r in filtered:
        reg = r[4] if len(r) > 4 else "Неизвестно"  # Region column
        regions[reg] = regions.get(reg, 0) + 1
    
    period_label = cutoff.strftime("%d.%m.%Y")
    text = (
        "📊 <b>Общая статистика</b>\n\n"
        f"Период: последние {DATA_RETENTION_DAYS} дней (с {period_label})\n"
        f"Всего заключений: {total}\n\n<b>По регионам:</b>\n"
    )
    for reg, count in sorted(regions.items(), key=lambda x: x[1], reverse=True):
        text += f"• {reg}: {count}\n"
    
    # Add back button
    keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data="admin_refresh", style='primary')]]
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
        [InlineKeyboardButton("💾 Скачать БД", callback_data="admin_download_db", style='primary')],
        [InlineKeyboardButton("♻️ Восстановить из бэкапа", callback_data="admin_restore_db", style='danger')],
        [InlineKeyboardButton("♻️ Сброс статистики (мягко)", callback_data="admin_stats_reset", style='danger')],
        [InlineKeyboardButton("◀️ Назад", callback_data="admin_refresh", style='primary')]
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
        [InlineKeyboardButton("📊 По регионам", callback_data="analytics_regions", style='primary')],
        [InlineKeyboardButton("📈 По подразделениям", callback_data="analytics_departments", style='primary')],
        [InlineKeyboardButton("👥 Топ пользователей", callback_data="analytics_top_users", style='primary')],
        [InlineKeyboardButton("📅 По дням", callback_data="analytics_daily", style='primary')],
        [InlineKeyboardButton("🗓 За период", callback_data="analytics_select_period", style='primary')],
        [InlineKeyboardButton("◀️ Назад", callback_data="admin_refresh", style='primary')]
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
    
    keyboard = [[InlineKeyboardButton("◀️ Назад к аналитике", callback_data="admin_analytics", style='primary')]]
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
        keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="analytics_main", style='primary')])
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
    
    keyboard = [
        [
            InlineKeyboardButton("🌍 Этот месяц (регион)", callback_data="admin_dl_current", style='primary'),
            InlineKeyboardButton("🌍 Прошлый месяц (регион)", callback_data="admin_dl_last", style='primary')
        ]
    ]
    keyboard += DateFilter.get_keyboard("admin_archive_period")
    keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="admin_refresh", style='primary')])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.callback_query.edit_message_text(
        "📦 <b>Скачать архив</b>\n\n"
        "Выберите период и регион, либо используйте команду:\n"
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

        keyboard = [[InlineKeyboardButton("🌍 Все регионы", callback_data=f"admin_dl_region|{month}|all", style='primary')]]
        for idx, region in enumerate(regions):
            keyboard.append([InlineKeyboardButton(region, callback_data=f"admin_dl_region|{month}|{idx}", style='primary')])
        keyboard.append([InlineKeyboardButton("◀️ Назад к выбору месяца", callback_data="admin_download_month", style='primary')])

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

async def show_period_region_menu(update: Update, context: CallbackContext, start_date, end_date, label: str) -> None:
    """Ask admin to choose region for a custom period archive."""
    try:
        regions = list(REGION_TOPICS.keys())
        context.user_data["archive_period_start"] = start_date
        context.user_data["archive_period_end"] = end_date
        context.user_data["archive_period_label"] = label
        context.user_data["archive_regions"] = regions

        keyboard = [[InlineKeyboardButton("🌍 Все регионы", callback_data="admin_archive_region|all", style='primary')]]
        for idx, region in enumerate(regions):
            keyboard.append([InlineKeyboardButton(region, callback_data=f"admin_archive_region|{idx}", style='primary')])
        keyboard.append([InlineKeyboardButton("◀️ Назад к архиву", callback_data="admin_archive", style='primary')])

        if update.callback_query and update.callback_query.message:
            await update.callback_query.message.edit_text(
                f"📦 <b>Архив за {label}</b>\n\nВыберите регион:",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        else:
            await safe_reply(
                update,
                f"📦 <b>Архив за {label}</b>\n\nВыберите регион:",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
    except Exception as e:
        await safe_reply(update, f"Ошибка при показе регионов: {e}")

async def handle_period_region_choice(update: Update, context: CallbackContext, action: str) -> None:
    """Handle region selection for a custom period archive."""
    parts = action.split("|", 1)
    if len(parts) != 2:
        await safe_reply(update, "Неверный формат запроса архива.")
        return
    _, region_key = parts

    start_date = context.user_data.get("archive_period_start")
    end_date = context.user_data.get("archive_period_end")
    regions = context.user_data.get("archive_regions", list(REGION_TOPICS.keys()))
    label = context.user_data.get("archive_period_label", "")

    if not start_date or not end_date:
        await safe_reply(update, "Даты архива устарели. Выберите период заново.")
        return

    region = None
    if region_key != "all":
        try:
            idx = int(region_key)
            region = regions[idx]
        except (ValueError, IndexError):
            await safe_reply(update, "Не удалось определить регион.")
            return

    from modern_bot.handlers.reports import send_period_archive
    await send_period_archive(update, context, start_date, end_date, region)

    context.user_data.pop("archive_period_start", None)
    context.user_data.pop("archive_period_end", None)
    context.user_data.pop("archive_period_label", None)
    context.user_data.pop("archive_regions", None)

async def show_history(update: Update, context: CallbackContext) -> None:
    """Show history with back button."""
    from modern_bot.services.excel import read_excel_data
    from modern_bot.utils.formatters import format_history_list
    from modern_bot.services.retention import get_effective_cutoff
    from modern_bot.utils.validators import parse_date_str
    from datetime import datetime
    
    records = await read_excel_data()
    cutoff = await get_effective_cutoff()
    def _row_dt(value):
        if isinstance(value, datetime):
            return value
        return parse_date_str(str(value))

    filtered = [
        r for r in records
        if len(r) > 3 and r[3] and _row_dt(r[3]) and _row_dt(r[3]) >= cutoff
    ]
    text = format_history_list(filtered)
    
    keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data="admin_refresh", style='primary')]]
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
        [InlineKeyboardButton("➕ Добавить пользователя", callback_data="users_add", style='primary')],
        [InlineKeyboardButton("➖ Удалить пользователя", callback_data="users_remove", style='danger')],
        [InlineKeyboardButton("📋 Список пользователей", callback_data="users_list", style='primary')],
        [InlineKeyboardButton("◀️ Назад", callback_data="admin_refresh", style='primary')]
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
        [InlineKeyboardButton("➕ Добавить админа", callback_data="admins_add", style='primary')],
        [InlineKeyboardButton("➖ Удалить админа", callback_data="admins_remove", style='danger')],
        [InlineKeyboardButton("🔄 Обновить список", callback_data="admins_refresh", style='primary')],
        [InlineKeyboardButton("◀️ Назад", callback_data="admin_refresh", style='primary')]
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
        keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data="admin_users", style='primary')]]
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
