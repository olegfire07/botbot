import asyncio
import inspect
import logging
import os
from telegram import Update, BotCommand, BotCommandScopeDefault, BotCommandScopeChat, ReplyKeyboardRemove
from telegram.ext import Application, CommandHandler, MessageHandler, filters, PicklePersistence, ConversationHandler, CallbackQueryHandler, ApplicationHandlerStop
from modern_bot.config import load_bot_token
from modern_bot.database.db import init_db, close_db
from modern_bot.utils.files import clean_temp_files, backup_database
from modern_bot.handlers.common import process_network_recovery
from modern_bot.handlers.admin import add_admin_handler, broadcast_handler, is_admin, load_admin_ids
from modern_bot.handlers.commands import start_handler, menu_handler
from modern_bot.handlers.help import help_handler
from modern_bot.handlers.reports import (
    history_handler, download_month_handler, stats_handler, stats_period_handler
)
from modern_bot.utils.logger import setup_logger

from modern_bot.api import start_api_server, stop_api_server
logger = setup_logger()


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        logger.warning(f"Invalid {name}={raw!r}, using default {default}")
        return default


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        logger.warning(f"Invalid {name}={raw!r}, using default {default}")
        return default


def _configure_telegram_network(builder):
    """
    Configure Telegram network settings with backwards-compatible fallbacks.
    This keeps startup stable on temporary network hiccups.
    """
    connect_timeout = _env_float("TG_CONNECT_TIMEOUT", 20.0)
    read_timeout = _env_float("TG_READ_TIMEOUT", 30.0)
    write_timeout = _env_float("TG_WRITE_TIMEOUT", 30.0)
    pool_timeout = _env_float("TG_POOL_TIMEOUT", 20.0)
    updates_read_timeout = _env_float("TG_UPDATES_READ_TIMEOUT", 65.0)
    proxy = (
        os.getenv("TG_PROXY_URL", "").strip()
        or os.getenv("HTTPS_PROXY", "").strip()
        or os.getenv("https_proxy", "").strip()
        or os.getenv("HTTP_PROXY", "").strip()
        or os.getenv("http_proxy", "").strip()
    )

    timeout_methods = [
        ("connect_timeout", connect_timeout),
        ("read_timeout", read_timeout),
        ("write_timeout", write_timeout),
        ("pool_timeout", pool_timeout),
        ("get_updates_connect_timeout", connect_timeout),
        ("get_updates_read_timeout", updates_read_timeout),
        ("get_updates_write_timeout", write_timeout),
        ("get_updates_pool_timeout", pool_timeout),
    ]
    has_any_timeout_method = any(callable(getattr(builder, name, None)) for name, _ in timeout_methods)

    proxy_method = getattr(builder, "proxy", None)
    proxy_url_method = getattr(builder, "proxy_url", None)
    has_proxy_method = callable(proxy_method) or callable(proxy_url_method)

    # PTB forbids combining ApplicationBuilder.request(...) with builder timeout kwargs.
    # Prefer builder-native methods when available.
    use_builder_native = has_any_timeout_method and (not proxy or has_proxy_method)

    if use_builder_native:
        for method_name, value in timeout_methods:
            method = getattr(builder, method_name, None)
            if callable(method):
                builder = method(value)

        if proxy:
            if callable(proxy_method):
                builder = proxy_method(proxy)
            elif callable(proxy_url_method):
                builder = proxy_url_method(proxy)
    else:
        try:
            from telegram.request import HTTPXRequest

            params = inspect.signature(HTTPXRequest.__init__).parameters
            request_kwargs = {}
            if "connect_timeout" in params:
                request_kwargs["connect_timeout"] = connect_timeout
            if "read_timeout" in params:
                request_kwargs["read_timeout"] = read_timeout
            if "write_timeout" in params:
                request_kwargs["write_timeout"] = write_timeout
            if "pool_timeout" in params:
                request_kwargs["pool_timeout"] = pool_timeout

            if proxy:
                if "proxy" in params:
                    request_kwargs["proxy"] = proxy
                elif "proxy_url" in params:
                    request_kwargs["proxy_url"] = proxy

            request = HTTPXRequest(**request_kwargs)
            updates_kwargs = dict(request_kwargs)
            if "read_timeout" in params:
                updates_kwargs["read_timeout"] = updates_read_timeout
            get_updates_request = HTTPXRequest(**updates_kwargs)

            request_method = getattr(builder, "request", None)
            if callable(request_method):
                builder = request_method(request)

            get_updates_request_method = getattr(builder, "get_updates_request", None)
            if callable(get_updates_request_method):
                builder = get_updates_request_method(get_updates_request)
        except Exception as e:
            logger.warning(f"Could not create explicit HTTPXRequest config: {e}")

    logger.info(
        "Telegram network config: connect=%.1fs read=%.1fs updates_read=%.1fs proxy=%s",
        connect_timeout,
        read_timeout,
        updates_read_timeout,
        "on" if proxy else "off",
    )
    return builder


def _run_polling_resilient(application: Application):
    """
    Run polling with compatibility-aware kwargs.
    bootstrap_retries=-1 keeps retries inside PTB for startup/network blips.
    """
    poll_interval = _env_float("TG_POLL_INTERVAL", 1.0)
    poll_timeout = _env_float("TG_POLL_TIMEOUT", 30.0)
    bootstrap_retries = _env_int("TG_BOOTSTRAP_RETRIES", -1)

    desired_kwargs = {
        "poll_interval": poll_interval,
        "timeout": poll_timeout,
        "bootstrap_retries": bootstrap_retries,
        "close_loop": False,
    }

    signature = inspect.signature(application.run_polling)
    supported_kwargs = {
        key: value
        for key, value in desired_kwargs.items()
        if key in signature.parameters
    }

    if "allowed_updates" in signature.parameters and hasattr(Update, "ALL_TYPES"):
        supported_kwargs["allowed_updates"] = Update.ALL_TYPES

    logger.info(
        "run_polling options: poll_interval=%.1fs timeout=%.1fs bootstrap_retries=%s",
        poll_interval,
        poll_timeout,
        bootstrap_retries if "bootstrap_retries" in supported_kwargs else "default",
    )
    application.run_polling(**supported_kwargs)

async def clean_temp_files_job(context):
    await asyncio.to_thread(clean_temp_files, 3600)

async def clean_archives_job(context):
    from modern_bot.services.retention import run_retention_cleanup
    await run_retention_cleanup()

async def backup_database_job(context):
    await asyncio.to_thread(backup_database)

async def network_recovery_job(context):
    await process_network_recovery(context.application.bot)

async def error_handler(update, context):
    logger.error(f"Update {update} caused error {context.error}", exc_info=context.error)

async def track_user_middleware(update, context):
    """Automatically track all users who interact with the bot."""
    if update.effective_user:
        from modern_bot.handlers.user_management import add_user
        user = update.effective_user
        await add_user(
            user_id=user.id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name
        )

async def blocked_guard(update, context):
    """Stop processing updates for blocked users."""
    user = update.effective_user
    if not user:
        return
    from modern_bot.config import SUPER_ADMIN_ID
    if user.id == SUPER_ADMIN_ID:
        return
    from modern_bot.database.db import is_user_blocked
    if not await is_user_blocked(user.id):
        return
    message = "⛔ Доступ к боту ограничен. Обратитесь к администратору."
    try:
        if update.callback_query:
            await update.callback_query.answer("⛔ Доступ ограничен", show_alert=True)
        if update.effective_message:
            await update.effective_message.reply_text(message, reply_markup=ReplyKeyboardRemove())
        elif update.effective_chat:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=message,
                reply_markup=ReplyKeyboardRemove()
            )
    except Exception as e:
        logger.warning(f"Failed to notify blocked user {user.id}: {e}")
    raise ApplicationHandlerStop


async def post_init(application: Application):
    """
    Post initialization hook to prepare dependencies and start the API server.
    Keeps DB and API on the same event loop that the bot uses.
    """
    await init_db()
    await configure_bot_commands(application.bot)
    await start_api_server(application.bot)


async def post_shutdown(application: Application):
    """
    Graceful shutdown order:
    1) Stop API server listener.
    2) Close DB connection.
    """
    await stop_api_server()
    await close_db()


async def configure_bot_commands(bot):
    """
    Configure Telegram menu commands for users and admins separately.
    """
    # Commands for regular users
    default_commands = [
        BotCommand("start", "📋 Создать заключение"),
        BotCommand("menu", "📱 Главное меню"),
        BotCommand("rank", "🏆 Мой рейтинг"),
        BotCommand("help", "💡 Помощь"),
    ]
    try:
        # Aggressive cleanup - delete ALL commands first
        await bot.delete_my_commands(scope=BotCommandScopeDefault())
        logger.info("🗑 Deleted old default commands")
        
        # Small delay to ensure deletion propagates
        await asyncio.sleep(0.5)
        
        # Set new commands
        await bot.set_my_commands(default_commands, scope=BotCommandScopeDefault())
        logger.info(f"✅ Set {len(default_commands)} default commands for regular users")
    except Exception as e:
        logger.warning(f"Failed to set default commands: {e}")

    # Admin-specific commands (user management moved to /admin panel)
    try:
        from modern_bot.handlers.admin import admin_ids
        admin_commands = [
            BotCommand("start", "📋 Создать заключение"),
            BotCommand("menu", "📱 Главное меню"),
            BotCommand("rank", "🏆 Мой рейтинг"),
            BotCommand("admin", "🔧 Админ-панель"),
            BotCommand("stats", "📊 Статистика"),
            BotCommand("stats_period", "📈 Статистика за период"),
            BotCommand("history", "📚 История заключений"),
            BotCommand("download_month", "📥 Скачать архив"),
            BotCommand("help", "💡 Помощь"),
        ]
        for admin_id in admin_ids:
            try:
                # Delete old commands first
                await bot.delete_my_commands(scope=BotCommandScopeChat(chat_id=admin_id))
                await asyncio.sleep(0.3)
                # Set new commands
                await bot.set_my_commands(admin_commands, scope=BotCommandScopeChat(chat_id=admin_id))
                logger.info(f"✅ Set admin commands for {admin_id}")
            except Exception as admin_err:
                logger.warning(f"Failed to set admin commands for {admin_id}: {admin_err}")
        logger.info(f"✅ Set {len(admin_commands)} admin commands for {len(admin_ids)} admins")
                
    except Exception as e:
        logger.warning(f"Failed to set admin commands: {e}")

    await send_startup_notification(bot)

_STARTUP_NOTIFY_SENT = False

async def send_startup_notification(bot):
    """Notify super admin once on startup."""
    global _STARTUP_NOTIFY_SENT
    from datetime import datetime
    from modern_bot.config import SUPER_ADMIN_ID

    if _STARTUP_NOTIFY_SENT:
        return

    if not SUPER_ADMIN_ID:
        logger.warning("SUPER_ADMIN_ID is not set, skipping startup notification.")
        return

    _STARTUP_NOTIFY_SENT = True

    startup_message = (
        f"✅ <b>Бот запущен</b>\n"
        f"🕐 Время: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}\n"
        f"💻 Сервер: OK"
    )

    try:
        await bot.send_message(
            chat_id=SUPER_ADMIN_ID,
            text=startup_message,
            parse_mode="HTML"
        )
        logger.info(f"✅ Startup notification sent to super admin {SUPER_ADMIN_ID}")
    except Exception as e:
        logger.warning(f"Failed to notify super admin {SUPER_ADMIN_ID}: {e}")

from modern_bot.services.gamification import weekly_leaderboard_job, my_stats_command

def main():
    logger.debug("Starting main()...")
    # Load config
    token = load_bot_token()
    logger.debug("Token loaded.")
    load_admin_ids()
    logger.debug("Admins loaded.")

    # Persistence
    from modern_bot.config import BASE_DIR
    persistence_file = BASE_DIR / "bot_persistence.pickle"
    persistence = PicklePersistence(filepath=persistence_file)
    logger.debug("Persistence loaded.")

    # Build Application
    builder = (
        Application.builder()
        .token(token)
        .persistence(persistence)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
    )
    builder = _configure_telegram_network(builder)
    application = builder.build()
    logger.debug("App built.")

    # Jobs
    job_queue = application.job_queue

    job_queue.run_repeating(clean_temp_files_job, interval=3600, first=60)
    job_queue.run_repeating(clean_archives_job, interval=86400, first=120) # Run daily
    job_queue.run_repeating(backup_database_job, interval=86400, first=180) # Run daily
    
    # GAMIFICATION JOB (Friday at 18:00)
    # Note: time requires datetime.time object
    from datetime import time
    job_queue.run_daily(weekly_leaderboard_job, time=time(18, 0), days=(4,))

    # Handlers
    application.add_handler(CommandHandler("rank", my_stats_command)) # New command
    job_queue.run_repeating(network_recovery_job, interval=60, first=60)

    # Middleware
    from telegram.ext import TypeHandler
    application.add_handler(TypeHandler(Update, blocked_guard), group=-2)
    application.add_handler(TypeHandler(Update, track_user_middleware), group=-1)

    # Handlers
    application.add_handler(CommandHandler("start", start_handler))
    application.add_handler(CommandHandler("menu", menu_handler))
    application.add_handler(CommandHandler("help", help_handler))
    
    # Menu Buttons Handlers
    application.add_handler(MessageHandler(filters.Regex("^🏆 Мой рейтинг$"), my_stats_command))
    application.add_handler(MessageHandler(filters.Regex(r"^(?:\u2139\uFE0F?\s*)?Помощь$"), help_handler))
    
    # Admin Dashboard Button
    from modern_bot.handlers.admin_dashboard import admin_dashboard_handler
    application.add_handler(MessageHandler(filters.Regex("^⚙️ Админ-панель$"), admin_dashboard_handler))
    
    # Conversation Handler (Dialog Mode)
    from modern_bot.handlers.conversation import get_conversation_handler
    application.add_handler(get_conversation_handler())
    
    # Admin
    application.add_handler(CommandHandler("add_admin", add_admin_handler))
    application.add_handler(CommandHandler("broadcast", broadcast_handler))
    
    # User Management
    from modern_bot.handlers.user_commands import add_user_command, remove_user_command, remove_admin_command
    application.add_handler(CommandHandler("add_user", add_user_command))
    application.add_handler(CommandHandler("remove_user", remove_user_command))
    application.add_handler(CommandHandler("remove_admin", remove_admin_command))
    
    # Reports
    application.add_handler(CommandHandler("history", history_handler))
    application.add_handler(CommandHandler("download_month", download_month_handler))
    application.add_handler(CommandHandler("stats", stats_handler))
    application.add_handler(CommandHandler("stats_period", stats_period_handler))
    
    # Admin Dashboard (command + callback handler)
    from modern_bot.handlers.admin_dashboard import admin_dashboard_handler, get_admin_callback_handler
    application.add_handler(CommandHandler("admin", admin_dashboard_handler))
    application.add_handler(get_admin_callback_handler())
    
    # Interactive Admin Reply Handler
    from modern_bot.handlers.admin_interactive import handle_admin_reply
    application.add_handler(MessageHandler(
        filters.REPLY & (filters.TEXT | filters.PHOTO) & ~filters.COMMAND,
        handle_admin_reply
    ), group=10)

    # DB Upload Handler
    from modern_bot.handlers.db_upload import handle_db_upload_message
    application.add_handler(MessageHandler(
        filters.Document.ALL & filters.ChatType.PRIVATE,
        handle_db_upload_message
    ), group=11)
    
    # Admin Reconciliation
    from modern_bot.handlers.admin_reconciliation import (
        start_reconciliation, handle_reconciliation_file, handle_period_selection, handle_custom_dates, cancel_reconciliation, 
        WAITING_FOR_FILE, WAITING_FOR_PERIOD, WAITING_FOR_CUSTOM_DATES
    )
    
    reconciliation_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_reconciliation, pattern="^admin_reconcile$")],
        states={
            WAITING_FOR_FILE: [
                MessageHandler(filters.Document.ALL, handle_reconciliation_file)
            ],
            WAITING_FOR_PERIOD: [
                CallbackQueryHandler(handle_period_selection, pattern=r"^period\|")
            ],
            WAITING_FOR_CUSTOM_DATES: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_custom_dates)
            ]
        },
        fallbacks=[CommandHandler("cancel", cancel_reconciliation)],
    )
    application.add_handler(reconciliation_handler)
    
    # Admin Ticket Search
    from modern_bot.handlers.admin_search import (
        start_ticket_search, handle_ticket_input, cancel_search,
        WAITING_FOR_TICKET
    )
    
    search_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_ticket_search, pattern="^admin_search_ticket$")],
        states={
            WAITING_FOR_TICKET: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_ticket_input)
            ]
        },
        fallbacks=[CommandHandler("cancel", cancel_search)],
    )
    application.add_handler(search_handler)

    # Error Handler
    application.add_error_handler(error_handler)

    logger.info("Starting bot polling...")
    _run_polling_resilient(application)

if __name__ == "__main__":
    main()
