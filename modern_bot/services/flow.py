import logging
from pathlib import Path
from typing import Dict, Any, List
from telegram import Bot
from telegram.error import TelegramError

from modern_bot.config import REGION_TOPICS, MAIN_GROUP_CHAT_ID
from modern_bot.services.docx_gen import create_document
from modern_bot.services.excel import update_excel
from modern_bot.services.archive import archive_document
from modern_bot.handlers.common import send_document_from_path

logger = logging.getLogger(__name__)

async def finalize_conclusion(bot: Bot, user_id: int, user_name: str, data: Dict[str, Any], send_to_group: bool = True) -> None:
    """
    Generates the document, sends it to the user, updates Excel/Archive, 
    and optionally sends to the main group.
    """
    path = None
    try:
        # 1. Generate Document
        path = await create_document(user_id, user_name)
        
        # 1.5. Send notification about completion
        try:
            await bot.send_message(
                chat_id=user_id,
                text="🎉 <b>Документ готов!</b>\n\n"
                     "✅ Заключение успешно сформировано и отправляется вам.",
                parse_mode="HTML"
            )
        except Exception as e:
            logger.warning(f"Failed to send notification: {e}")
        
        # 2. Send to User
        await send_document_from_path(bot, user_id, path, caption="✅ Ваше заключение готово!")
        
        # 3. Finalize (Group, Excel, Archive)
        if send_to_group:
            region = data.get('region')
            topic_id = REGION_TOPICS.get(region)
            
            try:
                # Send to the specific topic if found, otherwise to the main group (general topic)
                # Format: Заключение от п. 385, билет: 03850006392, от 22.11.2025
                caption = (
                    f"📄 Заключение №{data.get('issue_number')} от п. {data.get('department_number')}, "
                    f"билет: {data.get('ticket_number')}, "
                    f"от {data.get('date')}\n"
                    f"🌍 Регион: {region}"
                )
                
                await send_document_from_path(
                    bot, 
                    MAIN_GROUP_CHAT_ID, 
                    path, 
                    message_thread_id=topic_id,
                    caption=caption
                )
            except Exception as e:
                logger.error(f"Failed to send to group: {e}")
                # We don't stop here, we continue to archive
            
            # Add user name to data for Excel tracking
            data['user_name'] = user_name
            await update_excel(data)
            await archive_document(path, data)
            
    except Exception as e:
        logger.error(f"Error in finalize_conclusion: {e}")
        raise e
    finally:
        # Cleanup
        if path and path.exists():
            try:
                path.unlink()
            except Exception:
                pass
