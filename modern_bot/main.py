import asyncio
import logging
from telegram import Update, BotCommand, BotCommandScopeDefault, BotCommandScopeChat
from telegram.ext import Application, CommandHandler, MessageHandler, filters, PicklePersistence, ConversationHandler, CallbackQueryHandler
from modern_bot.config import load_bot_token
from modern_bot.database.db import init_db, close_db
from modern_bot.utils.files import clean_temp_files, clean_old_archives, backup_database
from modern_bot.handlers.common import process_network_recovery
from modern_bot.handlers.admin import add_admin_handler, broadcast_handler, is_admin, load_admin_ids
from modern_bot.handlers.commands import start_handler, menu_handler
from modern_bot.handlers.help import help_handler
from modern_bot.handlers.reports import (
    history_handler, download_month_handler, stats_handler, stats_period_handler
)
from modern_bot.utils.logger import setup_logger

from modern_bot.api import start_api_server

logger = setup_logger()

async def clean_temp_files_job(context):
    await asyncio.to_thread(clean_temp_files, 3600)

async def clean_archives_job(context):
    await asyncio.to_thread(clean_old_archives)

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


async def post_init(application: Application):
    """
    Post initialization hook to prepare dependencies and start the API server.
    Keeps DB and API on the same event loop that the bot uses.
    """
    await init_db()
    await configure_bot_commands(application.bot)
    await start_api_server(application.bot)


async def configure_bot_commands(bot):
    """
    Configure Telegram menu commands for users and admins separately.
    """
    # Commands for regular users
    default_commands = [
        BotCommand("start", "📋 Создать заключение"),
        BotCommand("menu", "📱 Главное меню"),
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
        
        # Send startup notification to all admins
        from datetime import datetime
        startup_message = (
            f"✅ <b>Бот запущен</b>\n"
            f"🕐 Время: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}\n"
            f"💻 Сервер: OK"
        )
        for admin_id in admin_ids:
            try:
                await bot.send_message(
                    chat_id=admin_id,
                    text=startup_message,
                    parse_mode="HTML"
                )
            except Exception as e:
                logger.error(f"Failed to notify admin {admin_id}: {e}")
                
    except Exception as e:
        logger.warning(f"Failed to set admin commands: {e}")

def main():
    # Load config
    token = load_bot_token()
    load_admin_ids()

    # Persistence
    from modern_bot.config import BASE_DIR
    persistence_file = BASE_DIR / "bot_persistence.pickle"
    persistence = PicklePersistence(filepath=persistence_file)

    # Build Application
    application = Application.builder().token(token).persistence(persistence).post_init(post_init).post_shutdown(close_db).build()

    # Jobs
    job_queue = application.job_queue
    job_queue.run_repeating(clean_temp_files_job, interval=3600, first=60)
    job_queue.run_repeating(clean_archives_job, interval=86400, first=120) # Run daily
    job_queue.run_repeating(backup_database_job, interval=86400, first=180) # Run daily
    job_queue.run_repeating(network_recovery_job, interval=60, first=60)

    # Middleware
    from telegram.ext import TypeHandler
    application.add_handler(TypeHandler(Update, track_user_middleware), group=-1)

    # Handlers
    application.add_handler(CommandHandler("start", start_handler))
    application.add_handler(CommandHandler("menu", menu_handler))
    application.add_handler(CommandHandler("help", help_handler))
    
    # Menu Buttons Handlers
    application.add_handler(MessageHandler(filters.Regex("^ℹ️ Помощь$"), help_handler))
    
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
    
    # Admin Dashboard
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

    logger.info("Bot started.")
    application.run_polling()

if __name__ == "__main__":
    main()
