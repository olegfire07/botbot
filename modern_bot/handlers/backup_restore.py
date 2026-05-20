import asyncio
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext

logger = logging.getLogger(__name__)

def _format_period_value(value: str | None) -> str | None:
    if not value:
        return None
    value = value.strip()
    if not value:
        return None
    from datetime import datetime
    try:
        dt = datetime.fromisoformat(value.replace("Z", ""))
        return dt.strftime("%d.%m.%Y")
    except ValueError:
        # Fallback: keep only date part if present.
        return value.split(" ")[0]

def _collect_backup_stats(db_path):
    import sqlite3
    stats = {
        "processed_tickets": None,
        "user_data": None,
        "user_stats": None,
        "users": None,
        "quiz_attempts": None,
        "period_start": None,
        "period_end": None,
    }
    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()

        def safe_count(table: str):
            try:
                cur.execute(f"SELECT COUNT(*) FROM {table}")
                row = cur.fetchone()
                return row[0] if row else 0
            except sqlite3.Error:
                return None

        def safe_period(table: str, column: str):
            try:
                cur.execute(f"SELECT MIN({column}), MAX({column}) FROM {table}")
                row = cur.fetchone()
                if not row:
                    return None, None
                return row[0], row[1]
            except sqlite3.Error:
                return None, None

        stats["processed_tickets"] = safe_count("processed_tickets")
        stats["user_data"] = safe_count("user_data")
        stats["user_stats"] = safe_count("user_stats")
        stats["users"] = safe_count("users")
        stats["quiz_attempts"] = safe_count("quiz_attempts")

        start_raw, end_raw = safe_period("processed_tickets", "created_at")
        stats["period_start"] = _format_period_value(start_raw)
        stats["period_end"] = _format_period_value(end_raw)
        conn.close()
    except Exception as e:
        logger.warning("Failed to read backup stats for %s: %s", db_path, e)
    return stats

async def show_backups_menu(update: Update, context: CallbackContext) -> None:
    """Show list of available backups."""
    from modern_bot.config import BASE_DIR
    import os
    from datetime import datetime
    
    backups_dir = BASE_DIR / "backups"
    if not backups_dir.exists():
        await update.callback_query.answer("❌ Папка с бэкапами не найдена!", show_alert=True)
        return

    # Find DB backups
    backups = []
    for f in backups_dir.glob("user_data_*.db"):
        # Format: user_data_YYYY-MM-DD.db or user_data_YYYY-MM-DD_HH-MM-SS.db
        # We want to show date and size
        size_kb = f.stat().st_size / 1024
        mtime = datetime.fromtimestamp(f.stat().st_mtime).strftime("%d.%m.%Y %H:%M")
        backups.append({
            "name": f.name,
            "path": f,
            "label": f"{mtime} ({size_kb:.0f} KB)",
            "time": f.stat().st_mtime
        })
    
    # Sort by time desc
    backups.sort(key=lambda x: x["time"], reverse=True)
    
    # Take top 10
    backups = backups[:10]
    
    if not backups:
        await update.callback_query.answer("❌ Бэкапов не найдено!", show_alert=True)
        return

    stats_list = await asyncio.gather(
        *(asyncio.to_thread(_collect_backup_stats, b["path"]) for b in backups),
        return_exceptions=True
    )
    for b, stats in zip(backups, stats_list):
        b["stats"] = {} if isinstance(stats, Exception) else stats

    details_lines = []
    keyboard = []
    for idx, b in enumerate(backups, start=1):
        stats = b.get("stats") or {}
        tickets = stats.get("processed_tickets")
        drafts = stats.get("user_data")
        users = stats.get("users")
        user_stats = stats.get("user_stats")
        quiz = stats.get("quiz_attempts")
        period_start = stats.get("period_start")
        period_end = stats.get("period_end")

        def _fmt(value):
            return str(value) if value is not None else "н/д"

        period_label = None
        if period_start and period_end:
            period_label = f"{period_start} — {period_end}"
        elif period_start:
            period_label = period_start

        details_lines.append(f"<b>{idx}. {b['label']}</b>")
        details_lines.append(f"Заключения: {_fmt(tickets)} | Черновики: {_fmt(drafts)}")
        details_lines.append(f"Пользователи: {_fmt(users)} | Статистика: {_fmt(user_stats)} | Викторина: {_fmt(quiz)}")
        details_lines.append(f"Период заключений: {period_label or 'н/д'}")
        details_lines.append("")

        keyboard.append([
            InlineKeyboardButton(f"📄 {idx}. {b['label']}", callback_data=f"restore_backup|{b['name']}", style='primary')
        ])
    
    keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="admin_system", style='primary')])
    
    details_text = "\n".join(details_lines).strip()
    await update.callback_query.edit_message_text(
        "♻️ <b>Восстановление из бэкапа</b>\n\n"
        "Выберите файл для восстановления.\n"
        "Показываю состав бэкапа и период по дате создания заключений.\n"
        "⚠️ <b>Внимание:</b> Текущая база будет перезаписана (но мы сделаем её бэкап перед этим).\n\n"
        f"{details_text}",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def handle_backup_restore(update: Update, context: CallbackContext, action: str) -> None:
    """Handle backup restoration."""
    from modern_bot.config import BASE_DIR, DATABASE_FILE
    import shutil
    from datetime import datetime
    
    filename = action.split("|")[1]
    backup_path = BASE_DIR / "backups" / filename
    
    if not backup_path.exists():
        await update.callback_query.answer("❌ Файл бэкапа не найден!", show_alert=True)
        return
    
    await update.callback_query.answer("⏳ Восстанавливаю...", show_alert=False)
    status_msg = await update.callback_query.message.edit_text("⏳ Создаю страховочную копию текущей базы...")
    
    try:
        # 1. Safety backup of current DB
        if DATABASE_FILE.exists():
            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            safety_backup = BASE_DIR / "backups" / f"user_data_BEFORE_RESTORE_{timestamp}.db"
            shutil.copy2(DATABASE_FILE, safety_backup)
            await status_msg.edit_text(f"✅ Страховочная копия создана.\n⏳ Проверяю файл бэкапа...")
        
        # 2. Validate backup file (check SQLite magic bytes)
        with open(backup_path, 'rb') as f:
            header = f.read(16)
            if header != b'SQLite format 3\x00':
                await status_msg.edit_text("❌ Ошибка: Файл бэкапа поврежден (не является SQLite базой).")
                logger.error(f"Invalid backup file (magic bytes): {filename}")
                return
        
        # 3. Restore
        await status_msg.edit_text(f"✅ Файл валидный.\n⏳ Восстанавливаю {filename}...")
        shutil.copy2(backup_path, DATABASE_FILE)
        
        await status_msg.edit_text("✅ База успешно восстановлена!\n🔄 Перезагружаю бота...")
        
        # 4. Restart
        context.application.stop_running()
        
    except Exception as e:
        logger.error(f"Failed to restore backup: {e}")
        await status_msg.edit_text(f"❌ Ошибка при восстановлении: {e}")
