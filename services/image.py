from pathlib import Path
from PIL import Image, ImageOps
import logging
from config.settings import settings

logger = logging.getLogger(__name__)

def is_image_too_large(image_path: Path, max_size_mb: int = settings.MAX_PHOTO_SIZE_MB) -> bool:
    file_size_mb = image_path.stat().st_size / (1024 * 1024)
    return file_size_mb > max_size_mb

def compress_image(input_path: Path, output_path: Path, quality: int = 70) -> None:
    """Reliably compresses image, fixing orientation and converting to RGB."""
    with Image.open(input_path) as img:
        img = ImageOps.exif_transpose(img)
        if img.mode in ("RGBA", "LA", "P"):
            img = img.convert("RGB")
        img.save(output_path, "JPEG", quality=quality, optimize=True)

def clean_temp_files(max_age_seconds: int = 3600) -> None:
    """Removes old temporary files."""
    if settings.TEMP_PHOTOS_DIR.exists():
        import time
        now = time.time()
        for file in settings.TEMP_PHOTOS_DIR.iterdir():
            if not file.is_file():
                continue
            if file.stat().st_mtime < now - max_age_seconds:
                try:
                    file.unlink()
                    logger.info(f"Removed temp file: {file.name}")
                except Exception as e:
                    logger.error(f"Error removing file {file.name}: {e}")
