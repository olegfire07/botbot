import sys
import os
import subprocess
import asyncio
import traceback
import hashlib
import json
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
    
    project_lockfile = Path(__file__).parent / ".bot.lock"

    # A global lock per BOT_TOKEN prevents duplicate runs from different folders.
    # This is important when multiple backups/copies exist on the same machine.
    global_lockfile = None
    try:
        from modern_bot.config import load_bot_token
        token = load_bot_token()
        token_hash = hashlib.sha1(token.encode("utf-8")).hexdigest()[:12]
        global_lockfile = Path("/tmp") / f".bestbot_{token_hash}.lock"
    except Exception as e:
        # Keep startup working even if token cannot be read at this stage.
        print(f"⚠️  Не удалось создать глобальный lock по токену: {e}")

    def _read_pid(lock_path: Path):
        try:
            data = lock_path.read_text().strip()
            if not data:
                return None
            if data.startswith("{"):
                payload = json.loads(data)
                return int(payload.get("pid"))
            return int(data)
        except Exception:
            return None

    def _check_existing(lock_path: Path):
        if not lock_path or not lock_path.exists():
            return
        pid = _read_pid(lock_path)
        if not pid:
            print(f"⚠️  Поврежденный lockfile, удаляю: {lock_path}")
            lock_path.unlink(missing_ok=True)
            return
        try:
            os.kill(pid, 0)
            print(f"❌ ОШИБКА: Бот уже запущен (PID {pid})")
            print(f"   Lock: {lock_path}")
            print(f"   Чтобы остановить: kill {pid}")
            print(f"   Или принудительно: pkill -f run_modern_bot.py")
            sys.exit(1)
        except OSError:
            print(f"⚠️  Найден старый lockfile от процесса {pid} (не запущен): {lock_path}")
            lock_path.unlink(missing_ok=True)

    _check_existing(project_lockfile)
    _check_existing(global_lockfile)

    # Create lockfiles with PID (and path for better diagnostics).
    pid = os.getpid()
    project_lockfile.write_text(str(pid))
    if global_lockfile:
        global_payload = {
            "pid": pid,
            "path": str(Path(__file__).resolve()),
            "cwd": str(Path.cwd()),
        }
        global_lockfile.write_text(json.dumps(global_payload, ensure_ascii=False))

    print(f"🔒 Создан lockfile: PID {pid}")
    if global_lockfile:
        print(f"🔒 Создан глобальный lock: {global_lockfile}")
    
    # Cleanup on exit (only use atexit, no signal handlers to avoid conflicts)
    def cleanup_lockfile():
        for lock_path in (project_lockfile, global_lockfile):
            if not lock_path:
                continue
            if lock_path.exists():
                try:
                    lock_path.unlink()
                    print(f"🗑️  Удален lockfile: {lock_path}")
                except Exception:
                    pass
    
    import atexit
    atexit.register(cleanup_lockfile)

def main():
    # Ensure we run inside a virtual environment with dependencies installed
    script_dir = os.path.dirname(os.path.abspath(__file__))
    venv_candidates = [
        os.path.join(script_dir, ".venv"),
        os.path.join(script_dir, "venv"),
        os.path.abspath(os.path.join(script_dir, "..", ".venv")),
    ]
    for venv_path in venv_candidates:
        # Support both Windows (Scripts/python.exe) and Unix (bin/python3)
        if os.name == 'nt':  # Windows
            python_bin = os.path.join(venv_path, "Scripts", "python.exe")
        else:  # Unix/Linux/macOS
            python_bin = os.path.join(venv_path, "bin", "python3")
        
        if os.path.exists(python_bin):
            if os.path.realpath(sys.prefix) != os.path.realpath(venv_path):
                print(f"🔄 Switching to virtual environment: {python_bin}")
                if os.name == 'nt':
                    # On Windows, use subprocess instead of execv
                    import subprocess
                    sys.exit(subprocess.call([python_bin] + sys.argv))
                else:
                    os.execv(python_bin, [python_bin] + sys.argv)
            break
    
    # Check for existing instance BEFORE any imports
    check_lockfile()
    
    from modern_bot.main import main as bot_main
    
    # Auto-restart loop
    import time
    import logging
    
    logging.basicConfig(level=logging.INFO)
    # Prevent leaking secrets in logs (e.g. Telegram bot token in request URLs).
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logger = logging.getLogger("Restarter")
    
    restart_count = 0

    while True:
        # Ensure a fresh event loop on each restart to avoid "Event loop is closed".
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
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
        finally:
            try:
                if not loop.is_closed():
                    loop.close()
            finally:
                asyncio.set_event_loop(None)

if __name__ == "__main__":
    main()
