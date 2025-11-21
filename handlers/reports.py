from telegram import Update, ReplyKeyboardRemove
from telegram.ext import CallbackContext, ConversationHandler
from datetime import datetime
from typing import Optional, Dict, Any

from config.settings import settings
from services.excel import filter_records, create_excel_snapshot
from services.archive import get_archive_paths, create_zip_archive, archive_document
from services.document import create_document
from utils.helpers import parse_date_str, get_month_bounds, normalize_region_input
from utils.keyboards import build_keyboard_with_menu, build_region_filter_keyboard
from handlers.common import (
    REPORT_ACTION, REPORT_MONTH_INPUT, REPORT_MONTH_REGION,
    REPORT_PERIOD_START, REPORT_PERIOD_END, REPORT_PERIOD_REGION
)
from handlers.admin import is_admin

def _report_data(context: CallbackContext) -> Dict[str, Any]:
    return context.user_data.setdefault("report", {})

async def _reports_finish(update: Update, context: CallbackContext, message: str) -> int:
    context.user_data.pop("report", None)
    # We need to import build_main_menu here or pass it. 
    # To avoid circular imports, we can just send the message without menu or import inside function
    from utils.keyboards import build_main_menu
    await update.message.reply_text(message, reply_markup=build_main_menu(update.message.from_user.id))
    return ConversationHandler.END

async def reports_start_handler(update: Update, context: CallbackContext) -> int:
    if not is_admin(update.message.from_user.id):
        await update.message.reply_text("Недостаточно прав для работы с отчётами.")
        return ConversationHandler.END

    _report_data(context)
    markup = build_keyboard_with_menu([
        ["📦 Архив заключений"],
        ["📥 Выгрузка за месяц"],
        ["📈 Статистика за период"],
        ["📊 Сводка по регионам"],
        ["❌ Отмена"]
    ], one_time=True)
    await update.message.reply_text("Выберите действие для отчёта:", reply_markup=markup)
    return REPORT_ACTION

async def reports_action_handler(update: Update, context: CallbackContext) -> int:
    text = update.message.text.strip().lower()
    if "отмена" in text:
        return await _reports_finish(update, context, "❌ Отчёт отменён.")

    report = _report_data(context)
    if "архив" in text:
        report.clear()
        report["type"] = "archive"
        await update.message.reply_text(
            "Введите месяц в формате ММ.ГГГГ (например: 03.2025):",
            reply_markup=ReplyKeyboardRemove()
        )
        return REPORT_MONTH_INPUT
    if "выгруз" in text or "меся" in text:
        report.clear()
        report["type"] = "month"
        await update.message.reply_text(
            "Введите месяц в формате ММ.ГГГГ (например: 03.2025):",
            reply_markup=ReplyKeyboardRemove()
        )
        return REPORT_MONTH_INPUT
    if "свод" in text or ("регион" in text and "стат" not in text):
        report.clear()
        report["type"] = "region_summary"
        await update.message.reply_text(
            "Введите дату начала периода в формате ДД.ММ.ГГГГ:",
            reply_markup=ReplyKeyboardRemove()
        )
        return REPORT_PERIOD_START
    if "статист" in text or "период" in text:
        report.clear()
        report["type"] = "period"
        await update.message.reply_text(
            "Введите дату начала периода в формате ДД.ММ.ГГГГ:",
            reply_markup=ReplyKeyboardRemove()
        )
        return REPORT_PERIOD_START

    await update.message.reply_text("Выберите действие из меню отчётов.")
    return REPORT_ACTION

async def reports_month_input_handler(update: Update, context: CallbackContext) -> int:
    text = update.message.text.strip()
    if "отмена" in text.lower():
        return await _reports_finish(update, context, "❌ Отчёт отменён.")

    bounds = get_month_bounds(text)
    if not bounds:
        await update.message.reply_text("❗ Неверный формат. Укажите месяц как ММ.ГГГГ (например 03.2025).")
        return REPORT_MONTH_INPUT

    report = _report_data(context)
    report["month_text"] = text
    report["start_date"], report["end_date"] = bounds
    markup = build_region_filter_keyboard(settings.REGION_TOPICS, include_all=True)
    await update.message.reply_text("Выберите регион или 'Все регионы':", reply_markup=markup)
    return REPORT_MONTH_REGION

async def reports_month_region_handler(update: Update, context: CallbackContext) -> int:
    text = update.message.text.strip().lower()
    if "отмена" in text:
        return await _reports_finish(update, context, "❌ Отчёт отменён.")

    region: Optional[str]
    if "все" in text:
        region = None
    else:
        region = normalize_region_input(update.message.text)
        if not region:
            await update.message.reply_text("Выберите регион из списка или 'Все регионы'.")
            return REPORT_MONTH_REGION

    report = _report_data(context)
    month_text = report.get("month_text")
    start_date = report.get("start_date")
    end_date = report.get("end_date")

    if not month_text or not start_date or not end_date:
        return await _reports_finish(update, context, "❌ Ошибка состояния отчёта. Попробуйте ещё раз.")

    report_type = report.get("type", "month")
    
    if report_type == "archive":
        # Send archive
        archive_paths = await get_archive_paths(start_date, end_date, region)
        if not archive_paths:
            await update.message.reply_text(f"За {month_text} архивных заключений не найдено.")
        else:
            region_label = region or "Все регионы"
            timestamp = datetime.now().strftime("%d.%m.%Y_%H-%M-%S")
            zip_name = f"archive_{month_text}_{region_label}_{timestamp}.zip"
            zip_path = await create_zip_archive(archive_paths, zip_name)
            try:
                await update.message.reply_document(document=open(zip_path, 'rb'), caption=f"Архив заключений за {month_text} ({region_label})")
            finally:
                if zip_path.exists():
                    zip_path.unlink()

    else:
        # Send excel report
        filtered = await filter_records(start_date=start_date, end_date=end_date, region=region)
        if not filtered:
            await update.message.reply_text(f"За {month_text} записей не найдено.")
        else:
            region_label = region or "Все регионы"
            filepath = await create_excel_snapshot(filtered, f"conclusions_{month_text}_{region_label}")
            try:
                await update.message.reply_document(document=open(filepath, 'rb'), caption=f"Заключения за {month_text} ({region_label})")
            finally:
                if filepath.exists():
                    filepath.unlink()

    return await _reports_finish(update, context, "Готово. Возвращаюсь в меню.")

async def reports_period_start_handler(update: Update, context: CallbackContext) -> int:
    text = update.message.text.strip()
    if "отмена" in text.lower():
        return await _reports_finish(update, context, "❌ Отчёт отменён.")

    start_date = parse_date_str(text)
    if not start_date:
        await update.message.reply_text("❗ Неверный формат. Используйте ДД.ММ.ГГГГ (например 01.03.2025).")
        return REPORT_PERIOD_START

    report = _report_data(context)
    report["start_date"] = start_date
    await update.message.reply_text("Введите дату окончания периода в формате ДД.ММ.ГГГГ:")
    return REPORT_PERIOD_END

async def reports_period_end_handler(update: Update, context: CallbackContext) -> int:
    text = update.message.text.strip()
    if "отмена" in text.lower():
        return await _reports_finish(update, context, "❌ Отчёт отменён.")

    end_date = parse_date_str(text)
    if not end_date:
        await update.message.reply_text("❗ Неверный формат. Используйте ДД.ММ.ГГГГ (например 31.03.2025).")
        return REPORT_PERIOD_END

    report = _report_data(context)
    report["end_date"] = end_date
    report_type = report.get("type")
    start_date = report.get("start_date")
    
    if not start_date:
        return await _reports_finish(update, context, "❌ Ошибка состояния отчёта. Попробуйте ещё раз.")
        
    if report_type == "region_summary":
        # Send region summary
        filtered = await filter_records(start_date=start_date, end_date=end_date, region=None)
        if not filtered:
             await update.message.reply_text("За выбранный период записей не найдено.")
        else:
            totals = {}
            for row in filtered:
                region_name = row[4] or "Не указано"
                entry = totals.setdefault(region_name, {"count": 0, "total": 0.0})
                entry["count"] += 1
                try:
                    entry["total"] += float(row[7] or 0)
                except (TypeError, ValueError):
                    continue

            period_text = f"{start_date.strftime('%d.%m.%Y')} — {end_date.strftime('%d.%m.%Y')}"
            lines = []
            for region_name, stats in sorted(totals.items(), key=lambda item: item[1]["total"], reverse=True):
                count = int(stats["count"])
                total_val = int(stats["total"])
                average = int(stats["total"] / stats["count"]) if stats["count"] else 0
                lines.append(f"  {region_name}: {count} предмет(ов), сумма {total_val}, средняя {average}")

            await update.message.reply_text(
                "📊 Сводка по регионам:\n"
                f"Диапазон: {period_text}\n" + 
                "\n".join(lines)
            )
        return await _reports_finish(update, context, "Готово. Возвращаюсь в меню.")

    markup = build_region_filter_keyboard(settings.REGION_TOPICS, include_all=True)
    await update.message.reply_text("Выберите регион для фильтра или 'Все регионы':", reply_markup=markup)
    return REPORT_PERIOD_REGION

async def reports_period_region_handler(update: Update, context: CallbackContext) -> int:
    text = update.message.text.strip().lower()
    if "отмена" in text:
        return await _reports_finish(update, context, "❌ Отчёт отменён.")

    region: Optional[str]
    if "все" in text:
        region = None
    else:
        region = normalize_region_input(update.message.text)
        if not region:
            await update.message.reply_text("Выберите регион из списка или 'Все регионы'.")
            return REPORT_PERIOD_REGION

    report = _report_data(context)
    start_date = report.get("start_date")
    end_date = report.get("end_date")

    if not start_date or not end_date:
        return await _reports_finish(update, context, "❌ Ошибка состояния отчёта. Попробуйте ещё раз.")

    if start_date > end_date:
        start_date, end_date = end_date, start_date

    filtered = await filter_records(start_date=start_date, end_date=end_date, region=region)
    if not filtered:
        await update.message.reply_text("За выбранный период записей не найдено.")
    else:
        total_items = len(filtered)
        total_eval = 0
        regions_stats = {}
        for row in filtered:
            region_name = row[4] or "Не указано"
            regions_stats[region_name] = regions_stats.get(region_name, 0) + 1
            try:
                total_eval += int(row[7] or 0)
            except (TypeError, ValueError):
                continue

        period_text = f"{start_date.strftime('%d.%m.%Y')} — {end_date.strftime('%d.%m.%Y')}"
        region_lines = "\n".join([f"  {r_name}: {count}" for r_name, count in sorted(regions_stats.items(), key=lambda x: x[0])])
        region_filter_text = f"Фильтр по региону: {region}\n" if region else ""
        
        await update.message.reply_text(
            "📈 Статистика за период:\n"
            f"Диапазон: {period_text}\n"
            f"{region_filter_text}"
            f"Всего предметов: {total_items}\n"
            f"Суммарная оценка: {total_eval}\n\n"
            "Предметов по регионам:\n"
            f"{region_lines if region_lines else 'Нет данных'}"
        )

    return await _reports_finish(update, context, "Готово. Возвращаюсь в меню.")

async def reports_cancel_handler(update: Update, context: CallbackContext) -> int:
    return await _reports_finish(update, context, "❌ Отчёт отменён.")
