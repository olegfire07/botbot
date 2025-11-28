import sys
import os
import subprocess
import asyncio
import traceback
from datetime import datetime

# Add project root to python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

async def notify_admins(message: str):
    """Send notification to all admins via Telegram."""
    try:
        from modern_bot.config import load_bot_token
        from modern_bot.handlers.admin import load_admin_ids, admin_ids
        from telegram import Bot
        
        # Load admin IDs if not already loaded
        if not admin_ids:
            load_admin_ids()
        
        if not admin_ids:
            return
        
        token = load_bot_token()
        bot = Bot(token=token)
        
        for admin_id in admin_ids:
            try:
                await bot.send_message(
                    chat_id=admin_id,
                    text=message,
                    parse_mode="HTML"
                )
            except Exception as e:
                print(f"Failed to notify admin {admin_id}: {e}")
    except Exception as e:
        print(f"Failed to send admin notifications: {e}")

def main():
    # Check if we are running in venv
    venv_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".venv")
    if os.path.exists(venv_path):
        # If not running from venv, re-exec
        if sys.prefix != venv_path:
            python_bin = os.path.join(venv_path, "bin", "python3")
            if os.path.exists(python_bin):
                print(f"🔄 Switching to virtual environment: {python_bin}")
                os.execv(python_bin, [python_bin] + sys.argv)
    
    from modern_bot.main import main as bot_main
    
    # Auto-restart loop
    import time
    import logging
    
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger("Restarter")
    
    restart_count = 0
    start_time = datetime.now()

    while True:
        try:
            logger.info("🚀 Starting bot...")
            
            # Notify admins on startup
            if restart_count == 0:
                asyncio.run(notify_admins(
                    f"✅ <b>Бот запущен</b>\n"
                    f"🕐 Время: {start_time.strftime('%d.%m.%Y %H:%M:%S')}\n"
                    f"💻 Сервер: OK"
                ))
            else:
                asyncio.run(notify_admins(
                    f"🔄 <b>Бот перезапущен</b>\n"
                    f"📊 Попытка #{restart_count}\n"
                    f"🕐 Время: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}"
                ))
            
            bot_main()
            
        except KeyboardInterrupt:
            logger.info("🛑 Bot stopped by user.")
            asyncio.run(notify_admins(
                f"🛑 <b>Бот остановлен вручную</b>\n"
                f"🕐 Время: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}"
            ))
            break
            
        except Exception as e:
            restart_count += 1
            error_trace = traceback.format_exc()
            logger.error(f"⚠️ Bot crashed with error: {e}")
            logger.error(f"Traceback:\n{error_trace}")
            
            # Notify admins about crash
            error_message = (
                f"⚠️ <b>Бот упал!</b>\n\n"
                f"📊 Попытка #{restart_count}\n"
                f"🕐 Время: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}\n"
                f"❌ Ошибка: <code>{str(e)[:200]}</code>\n\n"
                f"🔄 Перезапуск через 5 секунд..."
            )
            asyncio.run(notify_admins(error_message))
            
            logger.info("🔄 Restarting in 5 seconds...")
            time.sleep(5)

if __name__ == "__main__":
    main()

