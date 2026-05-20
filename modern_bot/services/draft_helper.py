import os
import httpx
import logging
import asyncio
from typing import Optional
from telegram import Bot
from telegram.error import BadRequest

logger = logging.getLogger(__name__)

async def send_or_update_draft(bot: Bot, chat_id: int, text: str, message_id: Optional[int] = None) -> Optional[int]:
    """
    Отправляет предварительное сообщение и плавно допечатывает новые строки (стриминг).
    Анимация применяется только к последней строке, чтобы избежать эффекта "печати заново".
    """
    return_id = message_id
    
    try:
        if message_id:
            # Пытаемся анимировать допечатывание последней строки
            lines = text.split('\n')
            if len(lines) > 1 and '🔄' in text:
                base_text = '\n'.join(lines[:-1])
                last_line = lines[-1]
                
                # Допечатываем последнюю строку частями
                words = last_line.split(' ')
                if len(words) > 2:
                    partial_text = base_text + "\n✍️ " + ' '.join(words[:2]) + "..."
                    try:
                        await bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=partial_text, parse_mode="Markdown")
                        await asyncio.sleep(0.3)
                    except BadRequest:
                        pass
                        
            # Финальный текст
            try:
                await bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=text, parse_mode="Markdown")
            except BadRequest:
                pass # Сообщение не изменилось
        else:
            msg = await bot.send_message(chat_id=chat_id, text=text, parse_mode="Markdown")
            return_id = msg.message_id
            
    except Exception as e:
        logger.warning(f"Error in UI streaming (editMessageText): {e}")

    return return_id
