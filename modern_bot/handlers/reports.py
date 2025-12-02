import logging
from datetime import datetime
from telegram import Update
from telegram.ext import CallbackContext
from modern_bot.handlers.common import safe_reply, send_document_from_path
from modern_bot.handlers.admin import is_admin
from modern_bot.services.excel import read_excel_data, create_excel_snapshot
from modern_bot.services.archive import get_archive_paths, create_archive_zip
from modern_bot.utils.validators import get_month_bounds, match_region_name, parse_date_str

logger = logging.getLogger(__name__)

async def history_handler(update: Update, context: CallbackContext) -> None:
    if not is_admin(update.effective_user.id):
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

async def send_month_archive(update: Update, context: CallbackContext, month_text: str, region: str = None) -> None:
    """Helper to send month archive."""
    logger.info(f"send_month_archive called: month={month_text}, region={region}")
    
    # Направляем уведомления и файл инициатору, плюс дублируем в сообщение панели, если это callback.
    chat_id = update.effective_user.id if update.effective_user else (update.effective_chat.id if update.effective_chat else None)
    query = getattr(update, "callback_query", None)
    logger.info(f"Chat ID: {chat_id}, Has callback_query: {query is not None}")

    async def notify(text: str, alert: bool = False):
        logger.info(f"Notifying: {text} (alert={alert})")
        # 1) Всплывающее уведомление на кнопке
        if query:
            try:
                await query.answer(text if alert else None, show_alert=alert)
            except Exception as e:
                logger.error(f"Failed to answer callback query: {e}")
        # 2) Ответ в чате (reply или send_message)
        sent = await safe_reply(update, text)
        if not sent and chat_id:
            try:
                await context.bot.send_message(chat_id=chat_id, text=text)
            except Exception as e:
                logger.error(f"Failed to send message: {e}")

    bounds = get_month_bounds(month_text)
    if not bounds:
        await notify("Неверный формат даты.")
        return
    
    start, end = bounds
    logger.info(f"Date bounds: {start} to {end}")
    
    paths = await get_archive_paths(start, end, region)
    logger.info(f"Found {len(paths)} archive files")
    
    if not paths:
        await notify(f"Архивы за {month_text}" + (f" ({region})" if region else "") + " не найдены.", alert=True)
        return

    await notify(f"⏳ Формирую архив за {month_text} ({len(paths)} файлов)...")
    try:
        filename_prefix = f"archive_{month_text}" + (f"_{region}" if region else "")
        zip_path = await create_archive_zip(paths, filename_prefix)
        logger.info(f"Archive ZIP created: {zip_path}")
    except Exception as e:
        logger.error(f"Failed to create archive: {e}", exc_info=True)
        await notify(f"❌ Не удалось сформировать архив: {e}")
        return

    if not chat_id:
        await notify("❌ Не удалось определить чат для отправки архива.")
        return

    try:
        logger.info(f"Sending archive to chat {chat_id}")
        await send_document_from_path(
            context.bot,
            chat_id,
            zip_path,
            caption=f"📦 Архив {month_text}" + (f" ({region})" if region else "")
        )
        logger.info("Archive sent successfully")
    except Exception as e:
        logger.error(f"Failed to send archive: {e}", exc_info=True)
        await notify(f"❌ Ошибка отправки архива: {e}")
    finally:
        try:
            if zip_path.exists():
                zip_path.unlink()
                logger.info(f"Cleaned up ZIP file: {zip_path}")
        except Exception as e:
            logger.error(f"Failed to cleanup ZIP: {e}")

async def send_period_archive(update: Update, context: CallbackContext, start: datetime, end: datetime, region: str = None) -> None:
    """Helper to send archive for a specific period."""
    from datetime import datetime
    
    chat_id = update.effective_user.id if update.effective_user else (update.effective_chat.id if update.effective_chat else None)
    query = getattr(update, "callback_query", None)

    async def notify(text: str, alert: bool = False):
        if query:
            try:
                await query.answer(text if alert else None, show_alert=alert)
            except Exception as e:
                logger.error(f"Failed to answer callback query: {e}")
        sent = await safe_reply(update, text)
        if not sent and chat_id:
            try:
                await context.bot.send_message(chat_id=chat_id, text=text)
            except Exception as e:
                logger.error(f"Failed to send message: {e}")

    paths = await get_archive_paths(start, end, region)
    
    period_str = f"{start.strftime('%d.%m.%Y')}-{end.strftime('%d.%m.%Y')}"
    
    if not paths:
        await notify(f"Архивы за {period_str}" + (f" ({region})" if region else "") + " не найдены.", alert=True)
        return

    await notify(f"⏳ Формирую архив за {period_str} ({len(paths)} файлов)...")
    try:
        filename_prefix = f"archive_{period_str}" + (f"_{region}" if region else "")
        zip_path = await create_archive_zip(paths, filename_prefix)
    except Exception as e:
        logger.error(f"Failed to create archive: {e}", exc_info=True)
        await notify(f"❌ Не удалось сформировать архив: {e}")
        return

    if not chat_id:
        await notify("❌ Не удалось определить чат для отправки архива.")
        return

    try:
        await send_document_from_path(
            context.bot,
            chat_id,
            zip_path,
            caption=f"📦 Архив {period_str}" + (f" ({region})" if region else "")
        )
    except Exception as e:
        logger.error(f"Failed to send archive: {e}", exc_info=True)
        await notify(f"❌ Ошибка отправки архива: {e}")
    finally:
        try:
            if zip_path.exists():
                zip_path.unlink()
        except Exception as e:
            logger.error(f"Failed to cleanup ZIP: {e}")

async def download_month_handler(update: Update, context: CallbackContext) -> None:
    if not is_admin(update.effective_user.id):
        await safe_reply(update, "Доступ запрещен.")
        return

    if not context.args:
        await safe_reply(update, "Использование: /download_month ММ.ГГГГ [Регион]")
        return

    month_text = context.args[0]
    region = None
    if len(context.args) > 1:
        candidate = " ".join(context.args[1:])
        region = match_region_name(candidate)
        if not region:
            await safe_reply(update, "Неизвестный регион.")
            return

    await send_month_archive(update, context, month_text, region)

async def stats_handler(update: Update, context: CallbackContext) -> None:
    user_id = update.effective_user.id
    
    # Only admins can use this command
    if not is_admin(user_id):
        await safe_reply(update, "❌ Эта команда доступна только администраторам.")
        return
    
    records = await read_excel_data()
    total = len(records)
    
    # Simple stats by region
    regions = {}
    for r in records:
        reg = r[4]  # Region column
        regions[reg] = regions.get(reg, 0) + 1
        
    text = f"📊 **Общая статистика**:\nВсего заключений: {total}\n\n**По регионам**:\n"
    for reg, count in regions.items():
        text += f"{reg}: {count}\n"
            
    await safe_reply(update, text)

async def stats_period_handler(update: Update, context: CallbackContext) -> None:
    if not is_admin(update.effective_user.id):
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
