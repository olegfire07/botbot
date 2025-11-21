import logging
import asyncio
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ConversationHandler
from config.settings import settings
from database.db import db
from handlers.common import (
    start_handler, cancel_handler, menu_handler, help_handler,
    DEPARTMENT, ISSUE_NUMBER, TICKET_NUMBER, DATE, REGION, PHOTO, DESCRIPTION, EVALUATION,
    MORE_PHOTO, CONFIRMATION, TESTING
)
from handlers.admin import (
    help_admin_handler, add_admin_handler, history_handler, stats_handler, load_admin_ids
)
from handlers.reports import (
    reports_start_handler, reports_action_handler, reports_month_input_handler,
    reports_month_region_handler, reports_period_start_handler, reports_period_end_handler,
    reports_period_region_handler, reports_cancel_handler,
    REPORT_ACTION, REPORT_MONTH_INPUT, REPORT_MONTH_REGION,
    REPORT_PERIOD_START, REPORT_PERIOD_END, REPORT_PERIOD_REGION
)
from handlers.conversation import (
    get_department, get_issue_number, get_ticket_number, get_date, get_region,
    photo_handler, description_handler, evaluation_handler, more_photo_handler,
    confirmation_handler, test_choice_handler
)
from services.image import clean_temp_files

# Logging setup
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

async def post_shutdown(application: Application) -> None:
    await db.close()

async def clean_temp_files_job(context):
    await asyncio.to_thread(clean_temp_files, 3600)

def main():
    # Create directories
    settings.TEMP_PHOTOS_DIR.mkdir(exist_ok=True)
    settings.DOCS_DIR.mkdir(exist_ok=True)
    settings.ARCHIVE_DIR.mkdir(exist_ok=True)
    if not settings.ARCHIVE_INDEX_FILE.exists():
        settings.ARCHIVE_INDEX_FILE.write_text("[]", encoding="utf-8")

    # Load admins
    load_admin_ids()

    # Init DB loop
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(db.connect())

    application = Application.builder().token(settings.BOT_TOKEN).post_shutdown(post_shutdown).build()

    # Jobs
    job_queue = application.job_queue
    job_queue.run_repeating(clean_temp_files_job, interval=3600, first=60)

    # Handlers
    reports_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("reports", reports_start_handler)],
        states={
            REPORT_ACTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, reports_action_handler)],
            REPORT_MONTH_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, reports_month_input_handler)],
            REPORT_MONTH_REGION: [MessageHandler(filters.TEXT & ~filters.COMMAND, reports_month_region_handler)],
            REPORT_PERIOD_START: [MessageHandler(filters.TEXT & ~filters.COMMAND, reports_period_start_handler)],
            REPORT_PERIOD_END: [MessageHandler(filters.TEXT & ~filters.COMMAND, reports_period_end_handler)],
            REPORT_PERIOD_REGION: [MessageHandler(filters.TEXT & ~filters.COMMAND, reports_period_region_handler)],
        },
        fallbacks=[
            CommandHandler("cancel", reports_cancel_handler),
            CommandHandler("menu", reports_cancel_handler),
            MessageHandler(filters.Regex("^❌ Отмена$"), reports_cancel_handler)
        ],
        allow_reentry=True
    )

    from handlers.webapp import webapp_data_handler

    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("start", start_handler),
            MessageHandler(filters.Regex("^📝 Создать \(Текст\)$"), start_handler),
            MessageHandler(filters.StatusUpdate.WEB_APP_DATA, webapp_data_handler)
        ],
        states={
            DEPARTMENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_department)],
            ISSUE_NUMBER: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_issue_number)],
            TICKET_NUMBER: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_ticket_number)],
            DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_date)],
            REGION: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_region)],
            PHOTO: [MessageHandler((filters.PHOTO | filters.Document.IMAGE), photo_handler)],
            DESCRIPTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, description_handler)],
            EVALUATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, evaluation_handler)],
            MORE_PHOTO: [MessageHandler(filters.TEXT & ~filters.COMMAND, more_photo_handler)],
            CONFIRMATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, confirmation_handler)],
            TESTING: [MessageHandler(filters.TEXT & ~filters.COMMAND, test_choice_handler)],
        },
        fallbacks=[CommandHandler("cancel", cancel_handler)],
        allow_reentry=True
    )

    application.add_handler(reports_conv_handler)
    application.add_handler(conv_handler)
    
    application.add_handler(CommandHandler("menu", menu_handler))
    application.add_handler(CommandHandler("help", help_handler))
    application.add_handler(CommandHandler("help_admin", help_admin_handler))
    application.add_handler(CommandHandler("history", history_handler))
    application.add_handler(CommandHandler("stats", stats_handler))
    application.add_handler(CommandHandler("add_admin", add_admin_handler))

    logger.info("Bot started.")
    application.run_polling()

if __name__ == "__main__":
    main()
