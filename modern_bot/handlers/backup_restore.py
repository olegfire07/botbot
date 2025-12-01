import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext

logger = logging.getLogger(__name__)
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

    keyboard = []
    for b in backups:
        keyboard.append([InlineKeyboardButton(f"📄 {b['label']}", callback_data=f"restore_backup|{b['name']}")])
    
    keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="admin_system")])
    
    await update.callback_query.edit_message_text(
        "♻️ <b>Восстановление из бэкапа</b>\n\n"
        "Выберите файл для восстановления.\n"
        "⚠️ <b>Внимание:</b> Текущая база будет перезаписана (но мы сделаем её бэкап перед этим).",
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
