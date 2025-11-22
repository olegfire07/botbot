import re
import random
import string
import time
import logging
from pathlib import Path
from PIL import Image, ImageOps
from modern_bot.config import TEMP_PHOTOS_DIR

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
    """Removes old temp files."""
    if TEMP_PHOTOS_DIR.exists():
        now = time.time()
        for file in TEMP_PHOTOS_DIR.iterdir():
            if not file.is_file():
                continue
            if file.stat().st_mtime < now - max_age_seconds:
                try:
                    file.unlink()
                    logger.info(f"Removed temp file: {file.name}")
                except Exception as e:
                    logger.error(f"Error removing file {file.name}: {e}")
