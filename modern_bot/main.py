import asyncio
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters
from modern_bot.config import load_bot_token
from modern_bot.database.db import init_db, close_db
from modern_bot.utils.files import clean_temp_files
from modern_bot.handlers.common import process_network_recovery
from modern_bot.handlers.commands import start_handler
from modern_bot.handlers.help import help_handler
from modern_bot.handlers.admin import (
    add_admin_handler, broadcast_handler, load_admin_ids
)
from modern_bot.config import load_bot_token, MAIN_GROUP_CHAT_ID
from modern_bot.handlers.reports import (
    history_handler, download_month_handler, stats_handler, stats_period_handler
)
from modern_bot.utils.logger import setup_logger

from modern_bot.api import start_api_server

logger = setup_logger()

async def clean_temp_files_job(context):
    await asyncio.to_thread(clean_temp_files, 3600)

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
    Post initialization hook to start the API server.
    """
    await start_api_server(application.bot)

def main():
    # Load config
    token = load_bot_token()
    load_admin_ids()

    # Build Application
    application = Application.builder().token(token).post_init(post_init).post_shutdown(close_db).build()

    # Init DB
    loop = asyncio.get_event_loop()
    loop.run_until_complete(init_db())

    # Jobs
    job_queue = application.job_queue
    job_queue.run_repeating(clean_temp_files_job, interval=3600, first=60)
    job_queue.run_repeating(network_recovery_job, interval=60, first=60)

    # Middleware
    from telegram.ext import TypeHandler
    application.add_handler(TypeHandler(Update, track_user_middleware), group=-1)

    # Handlers
    application.add_handler(CommandHandler("start", start_handler))
    application.add_handler(CommandHandler("help", help_handler))
    
    # Menu Buttons Handlers
    application.add_handler(MessageHandler(filters.Regex("^ℹ️ Помощь$"), help_handler))
    
    # Admin Dashboard Button
    from modern_bot.handlers.admin_dashboard import admin_dashboard_handler
    application.add_handler(MessageHandler(filters.Regex("^⚙️ Админ-панель$"), admin_dashboard_handler))
    
    # WebApp Data Handler
    from modern_bot.handlers.conversation import web_app_entry
    application.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, web_app_entry))
    
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
        filters.REPLY & filters.TEXT & ~filters.COMMAND,
        handle_admin_reply
    ), group=10)
    
    application.add_error_handler(error_handler)

    logger.info("Bot started.")
    application.run_polling()

if __name__ == "__main__":
    main()
