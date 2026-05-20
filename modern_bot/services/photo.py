import logging
import asyncio
import httpx
from pathlib import Path
from typing import Optional, Dict, Any

from modern_bot.config import TEMP_PHOTOS_DIR, MAX_PHOTO_SIZE_MB
from modern_bot.utils.files import generate_unique_filename

logger = logging.getLogger(__name__)

class PhotoService:
    @staticmethod
    async def download_photo(url_or_id: str, bot, client: Optional[httpx.AsyncClient] = None) -> Optional[Path]:
        """
        Downloads a photo from a Telegram File ID (tg:...) or a URL.
        Returns the path to the saved file, or None if failed.
        """
        if not url_or_id:
            return None
            
        TEMP_PHOTOS_DIR.mkdir(parents=True, exist_ok=True)
        unique_name = generate_unique_filename()
        file_path = TEMP_PHOTOS_DIR / unique_name

        # 0. Handle local storage reference
        if url_or_id.startswith('local:'):
            local_name = url_or_id[6:].strip()
            if not local_name:
                return None
            safe_name = Path(local_name).name
            if safe_name != local_name:
                logger.warning("Rejected unsafe local photo path: %s", local_name)
                return None
            local_path = TEMP_PHOTOS_DIR / safe_name
            if local_path.exists():
                return local_path
            logger.warning("Local photo not found: %s", safe_name)
            return None

        # 1. Handle Telegram File ID
        if url_or_id.startswith('tg:'):
            file_id = url_or_id[3:]
            try:
                # logger.info(f"Downloading from Telegram: {file_id}")
                new_file = await bot.get_file(file_id)
                await new_file.download_to_drive(custom_path=file_path)
                logger.info(f"Photo saved (TG): {file_path.name} ({file_path.stat().st_size} bytes)")
                return file_path
            except Exception as e:
                logger.error(f"Telegram download failed for {file_id}: {e}")
                return None

        # 2. Handle HTTP URL
        # Use provided client or create a temporary one
        should_close_client = False
        if client is None:
            client = httpx.AsyncClient(timeout=10.0, follow_redirects=True)
            should_close_client = True
            
        try:
            max_photo_bytes = MAX_PHOTO_SIZE_MB * 1024 * 1024
            
            # Retry logic
            for attempt in range(3):
                try:
                    # logger.info(f"Downloading photo from {url_or_id} (Attempt {attempt+1}/3)")
                    response = await client.get(url_or_id)
                    
                    if response.status_code != 200:
                        logger.warning(f"Download failed {url_or_id}: {response.status_code}")
                        if attempt < 2:
                            await asyncio.sleep(1)
                            continue
                        break

                    content_type = response.headers.get("Content-Type", "")
                    if not content_type.startswith("image/"):
                        logger.error(f"Invalid content type: {content_type}")
                        break
                        
                    if len(response.content) > max_photo_bytes:
                        logger.error(f"Photo too large: {len(response.content)} bytes")
                        break

                    await asyncio.to_thread(file_path.write_bytes, response.content)
                    logger.info(f"Photo saved (HTTP): {file_path.name} ({file_path.stat().st_size} bytes)")
                    return file_path
                    
                except httpx.TimeoutException:
                    if attempt < 2: await asyncio.sleep(1)
                except Exception as e:
                    logger.error(f"Error downloading {url_or_id}: {e}")
                    if attempt < 2: await asyncio.sleep(1)
                    
        finally:
            if should_close_client:
                await client.aclose()
                
        return None
