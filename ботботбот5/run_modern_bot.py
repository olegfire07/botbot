import sys
import os
import subprocess

# Add project root to python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

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

    while True:
        try:
            logger.info("🚀 Starting bot...")
            bot_main()
        except KeyboardInterrupt:
            logger.info("🛑 Bot stopped by user.")
            break
        except Exception as e:
            logger.error(f"⚠️ Bot crashed with error: {e}")
            logger.info("🔄 Restarting in 5 seconds...")
            time.sleep(5)

if __name__ == "__main__":
    main()
