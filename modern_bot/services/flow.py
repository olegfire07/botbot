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
from modern_bot.database.db import register_processed_ticket, update_user_stats
from modern_bot.services.draft_helper import send_or_update_draft

logger = logging.getLogger(__name__)

async def finalize_conclusion(bot: Bot, user_id: int, user_name: str, data: Dict[str, Any], send_to_group: bool = True, award_points: bool = True, msg_id: int = None) -> None:
    """
    Generates the document, sends it to the user, updates Excel/Archive, 
    and optionally sends to the main group.
    """
    path = None
    
    try:
        is_test = data.get('is_test', False)
        
        # Уведомляем о начале стриминга
        draft_text = "⏳ *Генерация заключения...*\n"
        if is_test:
            draft_text += "_(Тестовый режим)_\n"
        if not award_points:
            draft_text += "⚠️ _Дубликат: Баллы не будут начислены_\n"
        
        draft_text += "\n1️⃣ Сбор данных... 🔄"
        msg_id = await send_or_update_draft(bot, user_id, draft_text, msg_id)
        
        # 1. Generate Document
        path = await create_document(user_id, user_name)
        
        draft_text = "⏳ *Генерация заключения...*\n\n" \
                     "1️⃣ Сбор данных... ✅\n" \
                     "2️⃣ Формирование PDF/DOCX... 🔄"
        await send_or_update_draft(bot, user_id, draft_text, msg_id)
        
        # 1.5. Send notification about completion (Remove old static notification)
        # 2. Send to User
        await send_document_from_path(bot, user_id, path, caption="✅ Ваше заключение готово!")
        
        draft_text = "⏳ *Генерация заключения...*\n\n" \
                     "1️⃣ Сбор данных... ✅\n" \
                     "2️⃣ Формирование PDF/DOCX... ✅\n" \
                     "3️⃣ Отправка и сохранение базы... 🔄"
        await send_or_update_draft(bot, user_id, draft_text, msg_id)
        
        # 3. Finalize (Group, Excel, Archive)
        if send_to_group:
            region = data.get('region')
            topic_id = REGION_TOPICS.get(region)
            
            try:
                # Caption
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
            
            draft_text = "🎉 *Генерация заключения завершена!*\n\n" \
                         "1️⃣ Сбор данных... ✅\n" \
                         "2️⃣ Формирование PDF/DOCX... ✅\n" \
                         "3️⃣ Отправка и сохранение базы... ✅\n\n" \
                         "Документ отправлен в канал региона!"
            await send_or_update_draft(bot, user_id, draft_text, msg_id)
            
            # --- 4. SMART GUARD & GAMIFICATION ---
            # Only track valid, non-test submissions
            if not data.get('is_test', False):
                try:
                    # Register ticket to prevent duplicates
                    await register_processed_ticket(
                        ticket_number=str(data.get('ticket_number')),
                        issue_number=str(data.get('issue_number')),
                        date=data.get('date'),
                        user_id=user_id
                    )
                    
                    if award_points:
                        # Calculate total value
                        total_value = 0
                        for item in data.get('photo_desc', []):
                            try:
                                val = int(str(item.get('evaluation', '0')).replace(' ', ''))
                                total_value += val
                            except ValueError:
                                pass
                        
                        # Update stats
                        stats_res = await update_user_stats(user_id, total_value)
                        
                        # Notify rank up
                        if stats_res.get('rank_up'):
                            new_rank = stats_res.get('new_rank')
                            await bot.send_message(
                                chat_id=user_id,
                                text=f"🚀 <b>НОВЫЙ УРОВЕНЬ!</b>\n\nПоздравляем! Ваш статус повышен до: <b>{new_rank}</b> 🎉",
                                parse_mode="HTML"
                            )
                        
                        # Notify new achievements
                        new_ach = stats_res.get('new_achievements', [])
                        if new_ach:
                            ach_list = "\n".join([f"• {a}" for a in new_ach])
                            await bot.send_message(
                                chat_id=user_id,
                                text=f"🏅 <b>НОВЫЕ ДОСТИЖЕНИЯ!</b>\n\nВы получили следующие награды:\n{ach_list}",
                                parse_mode="HTML"
                            )
                except Exception as e:
                    logger.error(f"Gamification Error: {e}")
            # -------------------------------------
            
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
