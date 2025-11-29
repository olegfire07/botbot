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

def check_lockfile():
    """Check if another instance is already running."""
    from pathlib import Path
    
    lockfile = Path(__file__).parent / ".bot.lock"
    
    if lockfile.exists():
        try:
            # Read PID from lockfile
            pid = int(lockfile.read_text().strip())
            
            # Check if process is running (send signal 0 - doesn't kill, just checks)
            try:
                os.kill(pid, 0)
                # Process exists!
                print(f"❌ ОШИБКА: Бот уже запущен (PID {pid})")
                print(f"   Чтобы остановить: kill {pid}")
                print(f"   Или принудительно: pkill -f run_modern_bot.py")
                sys.exit(1)
            except OSError:
                # Process doesn't exist - stale lockfile
                print(f"⚠️  Найден старый lockfile от процесса {pid} (не запущен)")
                lockfile.unlink()
        except (ValueError, OSError) as e:
            print(f"⚠️  Поврежденный lockfile, удаляю...")
            lockfile.unlink()
    
    # Create lockfile with current PID
    lockfile.write_text(str(os.getpid()))
    print(f"🔒 Создан lockfile: PID {os.getpid()}")
    
    # Cleanup on exit (only use atexit, no signal handlers to avoid conflicts)
    def cleanup_lockfile():
        if lockfile.exists():
            try:
                lockfile.unlink()
                print(f"🗑️  Удален lockfile")
            except Exception:
                pass
    
    import atexit
    atexit.register(cleanup_lockfile)

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
    
    # Check for existing instance BEFORE any imports
    check_lockfile()
    
    from modern_bot.main import main as bot_main
    
    # Auto-restart loop
    import time
    import logging
    
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger("Restarter")
    
    restart_count = 0

    while True:
        try:
            logger.info("🚀 Starting bot...")
            bot_main()
            
        except KeyboardInterrupt:
            logger.info("🛑 Bot stopped by user.")
            print("\n🛑 Бот остановлен пользователем")
            break
            
        except Exception as e:
            restart_count += 1
            error_trace = traceback.format_exc()
            logger.error(f"⚠️ Bot crashed (attempt #{restart_count}): {e}")
            logger.error(f"Traceback:\n{error_trace}")
            logger.info("🔄 Restarting in 5 seconds...")
            time.sleep(5)

if __name__ == "__main__":
    main()

