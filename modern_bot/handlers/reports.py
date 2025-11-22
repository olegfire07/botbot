from telegram import Update
from telegram.ext import CallbackContext
from modern_bot.handlers.common import safe_reply, send_document_from_path
from modern_bot.handlers.admin import is_admin
from modern_bot.services.excel import read_excel_data, create_excel_snapshot
from modern_bot.services.archive import get_archive_paths, create_archive_zip
from modern_bot.utils.validators import get_month_bounds, match_region_name, parse_date_str

async def history_handler(update: Update, context: CallbackContext) -> None:
    if not is_admin(update.message.from_user.id):
        await safe_reply(update, "Access denied.")
        return
    records = await read_excel_data()
    if not records:
        await safe_reply(update, "History is empty.")
        return
    history_text = "📜 Last 10 records:\n\n" + "\n".join([
        f"Ticket: {r[0]}, #: {r[1]}, Dept: {r[2]}, Date: {r[3]}, Region: {r[4]}, Eval: {r[7]}"
        for r in records[-10:]
    ])
    await safe_reply(update, history_text)

async def download_month_handler(update: Update, context: CallbackContext) -> None:
    if not is_admin(update.message.from_user.id):
        await safe_reply(update, "Access denied.")
        return

    if not context.args:
        await safe_reply(update, "Usage: /download_month MM.YYYY [Region]")
        return

    month_text = context.args[0]
    bounds = get_month_bounds(month_text)
    if not bounds:
        await safe_reply(update, "Invalid format. Use MM.YYYY")
        return

    region = None
    if len(context.args) > 1:
        candidate = " ".join(context.args[1:])
        region = match_region_name(candidate)
        if not region:
            await safe_reply(update, "Unknown region.")
            return

    start, end = bounds
    paths = await get_archive_paths(start, end, region)
    if not paths:
        await safe_reply(update, "No archives found.")
        return

    zip_path = await create_archive_zip(paths, f"archive_{month_text}")
    try:
        await send_document_from_path(context.bot, update.effective_chat.id, zip_path, caption=f"Archive {month_text}")
    finally:
        if zip_path.exists():
            zip_path.unlink()
