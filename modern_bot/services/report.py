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
from modern_bot.services.photo import PhotoService

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
        logger.info(f"ReportService: Processing {len(items)} items")
        if len(items) > MAX_PHOTOS:
            logger.warning("Received %s items, trimming to MAX_PHOTOS=%s", len(items), MAX_PHOTOS)
            items = items[:MAX_PHOTOS]

        max_photo_bytes = MAX_PHOTO_SIZE_MB * 1024 * 1024
        http_timeout = httpx.Timeout(10.0)
        http_limits = httpx.Limits(max_connections=4, max_keepalive_connections=2)
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        
        async def download_item(client, item):
            photo_url = item.get('photo_url')
            if not photo_url:
                logger.warning("Item has no photo_url")
                return None
            
            # Use shared service
            # Note: create_report is called with 'bot' instance
            file_path = await PhotoService.download_photo(photo_url, bot, client)
            
            if file_path:
                photo_entry = {
                    'photo': str(file_path),
                    'description': item.get('description'),
                    'evaluation': item.get('evaluation')
                }
                return photo_entry
            return None

        async with httpx.AsyncClient(timeout=http_timeout, limits=http_limits, headers=headers, follow_redirects=True) as client:
            tasks = [download_item(client, item) for item in items]
            results = await asyncio.gather(*tasks)
            db_data['photo_desc'] = [r for r in results if r is not None]
            logger.info(f"Downloaded {len(db_data['photo_desc'])} photos successfully out of {len(items)} items")

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
                f"📄 Заключение №{data.get('issue_number')} от п. {data.get('department_number')}, "
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
                
        # --- CLEANUP TEMP PHOTOS ---
        try:
            for item in db_data.get('photo_desc', []):
                p_path = Path(item.get('photo', ''))
                if p_path.exists() and p_path.is_file():
                    # Security: Ensure we only delete from our temp dir
                    if TEMP_PHOTOS_DIR in p_path.parents:
                        p_path.unlink()
                        logger.info(f"Deleted temp photo: {p_path.name}")
        except Exception as e:
            logger.warning(f"Failed to cleanup temp photos: {e}")
        # ---------------------------

        return path
