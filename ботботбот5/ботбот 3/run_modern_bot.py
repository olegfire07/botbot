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
    bot_main()

if __name__ == "__main__":
    main()
