import json
from telegram import Update
from telegram.ext import CallbackContext
from config.settings import settings
from services.excel import read_excel_data
from typing import Set

# Admin management
admin_ids: Set[int] = set()

def load_admin_ids() -> None:
    global admin_ids
    ids: Set[int] = set()
    if settings.ADMIN_FILE.exists():
        try:
            with settings.ADMIN_FILE.open("r", encoding="utf-8") as f:
                data = json.load(f)
            ids = {int(item) for item in data if isinstance(item, int) or (isinstance(item, str) and item.isdigit())}
        except (OSError, json.JSONDecodeError):
            pass
    if not ids:
        ids = set(settings.DEFAULT_ADMIN_IDS)
        admin_ids = ids
        save_admin_ids()
    else:
        admin_ids = ids

def save_admin_ids() -> None:
    settings.ADMIN_FILE.parent.mkdir(parents=True, exist_ok=True)
    with settings.ADMIN_FILE.open("w", encoding="utf-8") as f:
        json.dump(sorted(admin_ids), f, ensure_ascii=False, indent=2)

def is_admin(user_id: int) -> bool:
    return user_id in admin_ids

async def help_admin_handler(update: Update, context: CallbackContext) -> None:
    if not is_admin(update.message.from_user.id):
        await update.message.reply_text("Команда доступна только администраторам.")
        return

    admin_help = (
        "🔧 Справка для администратора:\n\n"
        "• /history — последние 10 записей (по предметам).\n"
        "• /stats — совокупная статистика по всем данным.\n"
        "• /download_month ММ.ГГГГ [Регион] — архив DOCX за месяц.\n"
        "• /stats_period ДД.ММ.ГГГГ ДД.ММ.ГГГГ [Регион] — статистика за период.\n"
        "• /reports — мастер отчётов: архив заключений по месяцам, Excel-выгрузка, статистика по периоду, сводка по регионам.\n"
        "• /add_admin ID — добавить администратора.\n"
        "• /menu — открыть админское меню.\n"
        "• /help — инструкция по созданию заключения (для сотрудников)."
    )
    await update.message.reply_text(admin_help)

async def add_admin_handler(update: Update, context: CallbackContext) -> None:
    requester_id = update.message.from_user.id
    if not is_admin(requester_id):
        await update.message.reply_text("Недостаточно прав для добавления администратора.")
        return

    if not context.args:
        await update.message.reply_text("Использование: /add_admin <ID пользователя>")
        return

    try:
        new_admin_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❗ ID должен быть числом. Попробуйте ещё раз.")
        return

    if new_admin_id <= 0:
        await update.message.reply_text("❗ ID должен быть положительным числом.")
        return

    if new_admin_id == requester_id:
        await update.message.reply_text("Нельзя добавить самого себя.")
        return

    if new_admin_id in admin_ids:
        await update.message.reply_text("Этот пользователь уже имеет права администратора.")
        return

    admin_ids.add(new_admin_id)
    save_admin_ids()
    
    await update.message.reply_text(f"👥 Пользователь {new_admin_id} добавлен в список администраторов.")

async def history_handler(update: Update, context: CallbackContext) -> None:
    if not is_admin(update.message.from_user.id):
        await update.message.reply_text("Недостаточно прав для доступа к истории.")
        return
    records = await read_excel_data()
    if not records:
        await update.message.reply_text("История заключений пуста.")
        return
    history_text = "📜 Последние 10 записей (по предметам):\n\n" + "\n".join([
        f"Билет: {r[0]}, №: {r[1]}, Подр: {r[2]}, Дата: {r[3]}, Регион: {r[4]}, Оценка: {r[7]}"
        for r in records[-10:]
    ])
    await update.message.reply_text(history_text)

async def stats_handler(update: Update, context: CallbackContext) -> None:
    if not is_admin(update.message.from_user.id):
        await update.message.reply_text("Недостаточно прав для доступа к статистике.")
        return
    records = await read_excel_data()
    if not records:
        await update.message.reply_text("Нет данных для статистики.")
        return

    total_items = len(records)
    total_eval = 0.0
    regions = {}
    for rec in records:
        region_name = rec[4] or "Не указано"
        stats = regions.setdefault(region_name, {"count": 0, "total": 0.0})
        stats["count"] += 1
        try:
            value = float(rec[7] or 0)
        except (TypeError, ValueError):
            value = 0.0
        stats["total"] += value
        total_eval += value

    avg_eval = int(total_eval / total_items) if total_items else 0
    lines = []
    for region_name, stats in sorted(regions.items(), key=lambda item: item[1]["count"], reverse=True):
        count = int(stats["count"])
        total = int(stats["total"])
        average = int(stats["total"] / stats["count"]) if stats["count"] else 0
        lines.append(f"  {region_name}: {count} предмет(ов), сумма {total}, средняя {average}")

    top_region = lines[0].strip() if lines else "Нет данных"

    stats_text = (
        "📊 Сводная статистика:\n"
        f"Всего предметов: {total_items}\n"
        f"Суммарная оценка: {int(total_eval)}\n"
        f"Средняя оценка: {avg_eval}\n"
        f"Лидер по количеству: {top_region}\n\n"
        "Разбивка по регионам:\n"
        + "\n".join(lines)
    )
    await update.message.reply_text(stats_text)
