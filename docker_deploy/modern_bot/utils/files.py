import re
import random
import string
import time
import logging
from pathlib import Path
from PIL import Image, ImageOps
from modern_bot.config import TEMP_PHOTOS_DIR, DOCS_DIR, ARCHIVE_DIR, ARCHIVE_RETENTION_DAYS, BASE_DIR, DATABASE_FILE
import shutil

logger = logging.getLogger(__name__)

def generate_unique_filename(extension: str = ".jpg") -> str:
    return ''.join(random.choices(string.ascii_letters + string.digits, k=16)) + extension

def sanitize_filename(filename: str) -> str:
    """Cleans filename from forbidden characters."""
    cleaned = re.sub(r'[\/:*?"<>|]', '_', filename)
    reserved_names = {"CON", "PRN", "AUX", "NUL", "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9", "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9"}
    if cleaned.upper() in reserved_names:
        cleaned = f"_{cleaned}_"
    return cleaned[:150]

def is_image_too_large(image_path: Path, max_size_mb: int = 5) -> bool:
    file_size_mb = image_path.stat().st_size / (1024 * 1024)
    return file_size_mb > max_size_mb

def compress_image(input_path: Path, output_path: Path, quality: int = 70) -> None:
    """Compresses image, fixes orientation, and converts to RGB."""
    with Image.open(input_path) as img:
        img = ImageOps.exif_transpose(img)
        if img.mode in ("RGBA", "LA", "P"):
            img = img.convert("RGB")
        img.save(output_path, "JPEG", quality=quality, optimize=True)

def clean_temp_files(max_age_seconds: int = 3600) -> None:
    """Removes old temp files from photos and documents directories."""
    directories = [TEMP_PHOTOS_DIR, DOCS_DIR]
    
    for directory in directories:
        if not directory.exists():
            continue
            
        now = time.time()
        for file in directory.iterdir():
            if not file.is_file():
                continue
                
            # Skip .gitkeep or other hidden files if any
            if file.name.startswith('.'):
                continue
                
            if file.stat().st_mtime < now - max_age_seconds:
                try:
                    file.unlink()
                    logger.info(f"Removed temp file: {file.name}")
                except Exception as e:
                    logger.error(f"Error removing file {file.name}: {e}")

def clean_old_archives() -> None:
    """Removes archive files older than ARCHIVE_RETENTION_DAYS."""
    if not ARCHIVE_DIR.exists():
        return

    max_age_seconds = ARCHIVE_RETENTION_DAYS * 24 * 3600
    now = time.time()
    count = 0

    # Walk through all subdirectories in ARCHIVE_DIR
    for file in ARCHIVE_DIR.rglob('*'):
        if not file.is_file():
            continue
            
        # Skip index.json
        if file.name == "index.json":
            continue

        if file.stat().st_mtime < now - max_age_seconds:
            try:
                file.unlink()
                count += 1
                logger.info(f"Removed old archive: {file.name}")
            except Exception as e:
                logger.error(f"Error removing archive {file.name}: {e}")
    
    if count > 0:
        logger.info(f"Cleaned up {count} old archive files.")

def backup_database() -> None:
    """Creates daily backup of database and persistence file."""
    from datetime import datetime
    
    # Create backups directory
    backups_dir = BASE_DIR / "backups"
    backups_dir.mkdir(parents=True, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y-%m-%d")
    backup_count = 0
    
    # Backup database file
    if DATABASE_FILE.exists():
        try:
            backup_path = backups_dir / f"user_data_{timestamp}.db"
            shutil.copy2(DATABASE_FILE, backup_path)
            backup_count += 1
            logger.info(f"Database backed up to {backup_path}")
        except Exception as e:
            logger.error(f"Failed to backup database: {e}")
    
    # Backup persistence file
    persistence_file = BASE_DIR / "bot_persistence.pickle"
    if persistence_file.exists():
        try:
            backup_path = backups_dir / f"persistence_{timestamp}.pickle"
            shutil.copy2(persistence_file, backup_path)
            backup_count += 1
            logger.info(f"Persistence backed up to {backup_path}")
        except Exception as e:
            logger.error(f"Failed to backup persistence: {e}")
    
    # Clean old backups (keep last 90 days)
    max_age_seconds = 90 * 24 * 3600
    now = time.time()
    for file in backups_dir.glob('*'):
        if not file.is_file():
            continue
        if file.stat().st_mtime < now - max_age_seconds:
            try:
                file.unlink()
                logger.info(f"Removed old backup: {file.name}")
            except Exception as e:
                logger.error(f"Error removing backup {file.name}: {e}")
    
    if backup_count > 0:
        logger.info(f"Backup completed: {backup_count} files")
