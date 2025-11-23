from telegram import Update
from telegram.ext import CallbackContext
from modern_bot.handlers.common import safe_reply, send_document_from_path
from modern_bot.handlers.admin import is_admin
from modern_bot.services.excel import read_excel_data, create_excel_snapshot
from modern_bot.services.archive import get_archive_paths, create_archive_zip
from modern_bot.utils.validators import get_month_bounds, match_region_name, parse_date_str

async def history_handler(update: Update, context: CallbackContext) -> None:
    if not is_admin(update.message.from_user.id):
        await safe_reply(update, "Доступ запрещен.")
        return
    records = await read_excel_data()
    if not records:
        await safe_reply(update, "История пуста.")
        return
    history_text = "📜 Последние 10 записей:\n\n" + "\n".join([
        f"Билет: {r[0]}, №: {r[1]}, Подр: {r[2]}, Дата: {r[3]}, Регион: {r[4]}, Оценка: {r[7]}"
        for r in records[-10:]
    ])
    await safe_reply(update, history_text)

async def download_month_handler(update: Update, context: CallbackContext) -> None:
    if not is_admin(update.message.from_user.id):
        await safe_reply(update, "Доступ запрещен.")
        return

    if not context.args:
        await safe_reply(update, "Использование: /download_month ММ.ГГГГ [Регион]")
        return

    month_text = context.args[0]
    bounds = get_month_bounds(month_text)
    if not bounds:
        await safe_reply(update, "Неверный формат. Используйте ММ.ГГГГ")
        return

    region = None
    if len(context.args) > 1:
        candidate = " ".join(context.args[1:])
        region = match_region_name(candidate)
        if not region:
            await safe_reply(update, "Неизвестный регион.")
            return

    start, end = bounds
    paths = await get_archive_paths(start, end, region)
    if not paths:
        await safe_reply(update, "Архивы не найдены.")
        return

    zip_path = await create_archive_zip(paths, f"archive_{month_text}")
    try:
        await send_document_from_path(context.bot, update.effective_chat.id, zip_path, caption=f"Архив {month_text}")
    finally:
        if zip_path.exists():
            zip_path.unlink()

async def stats_handler(update: Update, context: CallbackContext) -> None:
    if not is_admin(update.message.from_user.id):
        return

    records = await read_excel_data()
    total = len(records)
    
    # Simple stats by region
    regions = {}
    for r in records:
        reg = r[4] # Region column
        regions[reg] = regions.get(reg, 0) + 1
        
    text = f"📊 **Общая статистика**:\nВсего заключений: {total}\n\n**По регионам**:\n"
    for reg, count in regions.items():
        text += f"{reg}: {count}\n"
        
    await safe_reply(update, text)

async def stats_period_handler(update: Update, context: CallbackContext) -> None:
    if not is_admin(update.message.from_user.id):
        return
        
    if len(context.args) < 2:
        await safe_reply(update, "Использование: /stats_period ДД.ММ.ГГГГ ДД.ММ.ГГГГ [Регион]")
        return
        
    start_str, end_str = context.args[0], context.args[1]
    start = parse_date_str(start_str)
    end = parse_date_str(end_str)
    
    if not start or not end:
        await safe_reply(update, "Неверный формат даты.")
        return
        
    region = None
    if len(context.args) > 2:
        region = match_region_name(" ".join(context.args[2:]))
        
    records = await read_excel_data()
    count = 0
    total_sum = 0
    
    for r in records:
        r_date = parse_date_str(r[3])
        if not r_date: continue
        
        if start <= r_date <= end:
            if region and r[4] != region:
                continue
            count += 1
            # Try to parse sum if needed, but for now just count
            
    filter_text = f" ({region})" if region else ""
    await safe_reply(update, f"📅 Статистика за {start_str} - {end_str}{filter_text}:\nНайдено заключений: {count}")
