import asyncio
import logging
from telegram.ext import Application, CommandHandler, MessageHandler, filters
from modern_bot.config import load_bot_token
from modern_bot.database.db import init_db, close_db
from modern_bot.utils.files import clean_temp_files
from modern_bot.handlers.common import process_network_recovery
from modern_bot.handlers.start import start_handler, web_app_data_handler, photo_upload_handler
from modern_bot.handlers.conversation import get_conversation_handler
from modern_bot.handlers.admin import (
    add_admin_handler, broadcast_handler, help_admin_handler, load_admin_ids
)
from modern_bot.handlers.reports import (
    history_handler, download_month_handler
)
from modern_bot.utils.logger import setup_logger

logger = setup_logger()

async def clean_temp_files_job(context):
    await asyncio.to_thread(clean_temp_files, 3600)

async def network_recovery_job(context):
    await process_network_recovery(context.application.bot)

async def error_handler(update, context):
    logger.error(f"Update {update} caused error {context.error}", exc_info=context.error)

def main():
    # Load config
    token = load_bot_token()
    load_admin_ids()

    # Build Application
    application = Application.builder().token(token).post_shutdown(close_db).build()

    # Init DB
    loop = asyncio.get_event_loop()
    loop.run_until_complete(init_db())

    # Jobs
    job_queue = application.job_queue
    job_queue.run_repeating(clean_temp_files_job, interval=3600, first=60)
    job_queue.run_repeating(network_recovery_job, interval=60, first=60)

    # Handlers
    application.add_handler(CommandHandler("start", start_handler))
    application.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, web_app_data_handler))
    
    # Legacy Conversation
    application.add_handler(get_conversation_handler())
    
    # Admin
    application.add_handler(CommandHandler("add_admin", add_admin_handler))
    application.add_handler(CommandHandler("broadcast", broadcast_handler))
    application.add_handler(CommandHandler("help_admin", help_admin_handler))
    
    # Reports
    application.add_handler(CommandHandler("history", history_handler))
    application.add_handler(CommandHandler("download_month", download_month_handler))
    
    # Photo upload (for Web App flow) - simplified for now
    # application.add_handler(MessageHandler(filters.PHOTO, photo_upload_handler))

    application.add_error_handler(error_handler)

    logger.info("Bot started.")
    application.run_polling()

if __name__ == "__main__":
    main()
