import logging
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from datetime import datetime

def setup_logger():
    """Setup logger with console and file output (daily rotation)."""
    # Create logs directory
    from modern_bot.config import BASE_DIR
    logs_dir = BASE_DIR / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    
    # Create logger
    logger = logging.getLogger("modern_bot")
    logger.setLevel(logging.INFO)
    
    # Avoid duplicate handlers
    if logger.handlers:
        return logger
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    console_handler.setFormatter(console_formatter)
    
    # File handler with daily rotation
    log_file = logs_dir / f"bot_{datetime.now().strftime('%Y-%m-%d')}.log"
    file_handler = TimedRotatingFileHandler(
        log_file,
        when='midnight',
        interval=1,
        backupCount=7,  # Keep 7 days of logs
        encoding='utf-8'
    )
    file_handler.setLevel(logging.INFO)
    file_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(file_formatter)
    
    # Add handlers
    logger.addHandler(console_handler)
    logger.addHandler(file_handler)
    
    return logger
