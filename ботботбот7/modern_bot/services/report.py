import logging
import asyncio
import httpx
from pathlib import Path
from typing import Dict, Any, Optional

from modern_bot.config import (
    TEMP_PHOTOS_DIR,
    MAIN_GROUP_CHAT_ID,
    REGION_TOPICS,
    MAX_PHOTOS,
    MAX_PHOTO_SIZE_MB,
)
from modern_bot.utils.files import generate_unique_filename
from modern_bot.services.docx_gen import create_document
from modern_bot.services.flow import send_document_from_path
from modern_bot.services.excel import update_excel
from modern_bot.services.archive import archive_document

logger = logging.getLogger(__name__)

class ReportService:
    @staticmethod
    async def create_report(data: Dict[str, Any], bot) -> Optional[Path]:
        """
        Orchestrates the report creation process:
        1. Downloads photos
        2. Generates DOCX
        3. Updates Excel/Archive
        4. Sends to Telegram
        """
        # 1. Prepare Data
        db_data = {
            'department_number': data['department_number'],
            'issue_number': data['issue_number'],
            'ticket_number': data['ticket_number'],
            'date': data['date'],
            'region': data['region'],
            'photo_desc': []
        }
        
        # 2. Download Photos (Parallel)
        TEMP_PHOTOS_DIR.mkdir(parents=True, exist_ok=True)
        items = data.get('items', [])
        if len(items) > MAX_PHOTOS:
            logger.warning("Received %s items, trimming to MAX_PHOTOS=%s", len(items), MAX_PHOTOS)
            items = items[:MAX_PHOTOS]

        max_photo_bytes = MAX_PHOTO_SIZE_MB * 1024 * 1024
        http_timeout = httpx.Timeout(10.0)
        http_limits = httpx.Limits(max_connections=4, max_keepalive_connections=2)
        
        async def download_item(client, item):
            photo_url = item.get('photo_url')
            if not photo_url:
                return None
            try:
                response = await client.get(photo_url)
                content_type = response.headers.get("Content-Type", "")
                content_length = response.headers.get("Content-Length")

                if response.status_code != 200:
                    logger.error(f"Failed to download photo from {photo_url}: {response.status_code}")
                    return None
                if not content_type.startswith("image/"):
                    logger.error(f"Invalid content type for {photo_url}: {content_type}")
                    return None
                if content_length and int(content_length) > max_photo_bytes:
                    logger.error(f"Photo too large (header) {photo_url}: {content_length} bytes")
                    return None
                if len(response.content) > max_photo_bytes:
                    logger.error(f"Photo too large (body) {photo_url}: {len(response.content)} bytes")
                    return None

                unique_name = generate_unique_filename()
                file_path = TEMP_PHOTOS_DIR / unique_name
                await asyncio.to_thread(file_path.write_bytes, response.content)
                return {
                    'photo': str(file_path),
                    'description': item.get('description'),
                    'evaluation': item.get('evaluation')
                }
            except httpx.HTTPError as e:
                logger.error(f"HTTP error downloading photo: {e}")
            except IOError as e:
                logger.error(f"IO error saving photo: {e}")
            except Exception as e:
                logger.error(f"Unexpected error downloading photo: {e}")
            return None

        async with httpx.AsyncClient(timeout=http_timeout, limits=http_limits) as client:
            tasks = [download_item(client, item) for item in items]
            results = await asyncio.gather(*tasks)
            db_data['photo_desc'] = [r for r in results if r is not None]

        # 3. Generate Document
        user_id = 0 # Web User
        user_name = "Web User"
        path = await create_document(user_id, user_name, db_data_override=db_data)
        
        # 4. Update Excel and Archive
        try:
            await update_excel(db_data)
            await archive_document(path, db_data)
        except Exception as e:
            logger.error(f"Failed to update Excel/Archive: {e}")

        # 5. Send to Group (if not test)
        is_test = data.get('is_test', False)
        if not is_test:
            region = data.get('region')
            topic_id = REGION_TOPICS.get(region)
            caption = (
                f"📄 Заключение от п. {data.get('department_number')}, "
                f"билет: {data.get('ticket_number')}, "
                f"от {data.get('date')}\n"
                f"🌍 Регион: {region}\n"
                f"(Создано через сайт)"
            )
            try:
                await send_document_from_path(
                    bot, 
                    MAIN_GROUP_CHAT_ID, 
                    path, 
                    message_thread_id=topic_id,
                    caption=caption
                )
            except Exception as e:
                logger.error(f"Failed to send to group: {e}")
                
        return path
