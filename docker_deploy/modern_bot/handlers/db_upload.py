import logging
from telegram import Update
from telegram.ext import CallbackContext
from modern_bot.handlers.admin import is_admin

logger = logging.getLogger(__name__)
async def handle_db_upload_message(update: Update, context: CallbackContext):
    """Handle database file upload."""
    user_id = update.effective_user.id
    if not is_admin(user_id):
        return

    # Check flag
    if not context.user_data.get('awaiting_db_upload'):
        return

    document = update.message.document
    if not document:
        return

    if not document.file_name.endswith('.db'):
        await update.message.reply_text("❌ Это не файл базы данных (.db). Пожалуйста, отправьте файл с расширением .db")
        return

    status_msg = await update.message.reply_text("⏳ Скачиваю и проверяю файл...")

    try:
        from modern_bot.config import DATABASE_FILE, BASE_DIR
        import shutil
        from datetime import datetime
        import os

        # 1. Download new file
        new_file = await document.get_file()
        
        # Check size (max 50MB)
        if new_file.file_size and new_file.file_size > 50 * 1024 * 1024:
             await status_msg.edit_text("❌ Файл базы данных слишком большой (>50MB).")
             return

        temp_path = BASE_DIR / "temp_upload.db"
        await new_file.download_to_drive(temp_path)

        # Check Magic Bytes (SQLite header)
        with open(temp_path, 'rb') as f:
            header = f.read(16)
            if header != b'SQLite format 3\x00':
                await status_msg.edit_text("❌ Это не валидный файл SQLite базы данных.")
                os.remove(temp_path)
                return

        # 2. Backup current DB
        if DATABASE_FILE.exists():
            backup_dir = BASE_DIR / "backups"
            backup_dir.mkdir(exist_ok=True)
            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            backup_path = backup_dir / f"user_data_BEFORE_UPLOAD_{timestamp}.db"
            shutil.copy2(DATABASE_FILE, backup_path)
            await status_msg.edit_text(f"✅ Бэкап создан: {backup_path.name}\n⏳ Применяю новую базу...")

        # 3. Replace DB
        # Close DB connection first? 
        # Ideally yes, but aiosqlite connection is managed by the app.
        # Replacing the file while open might be risky on some OS, but usually works on Unix.
        # Better to stop the app, but we are inside the app.
        # We will replace and restart immediately.
        
        shutil.move(temp_path, DATABASE_FILE)

        await status_msg.edit_text("✅ База успешно обновлена!\n🔄 Перезагружаю бота...")
        
        # Clear flag
        context.user_data['awaiting_db_upload'] = False
        
        # Restart bot
        context.application.stop_running()

    except Exception as e:
        logger.error(f"Failed to upload DB: {e}")
        await status_msg.edit_text(f"❌ Ошибка при обновлении базы: {e}")
        if os.path.exists(temp_path):
            os.remove(temp_path)
