import asyncio
import logging
import time
from typing import Dict, Any, Optional, Tuple, List
from telegram import Update
from telegram.error import RetryAfter, NetworkError, TelegramError, TimedOut
from telegram.ext import CallbackContext
from modern_bot.config import NETWORK_RECOVERY_INTERVAL, MAX_PENDING_RESENDS

logger = logging.getLogger(__name__)
network_recovery_lock = asyncio.Lock()
network_recovery_pending: Dict[int, Dict[str, Any]] = {}

async def mark_network_issue(chat_id: int, text: str, kwargs: Dict[str, Any]) -> None:
    async with network_recovery_lock:
        entry = network_recovery_pending.setdefault(
            chat_id,
            {"timestamp": time.time() - NETWORK_RECOVERY_INTERVAL, "messages": []}
        )
        messages: List[Tuple[str, Dict[str, Any]]] = entry.setdefault("messages", [])
        messages.append((text, kwargs))
        if len(messages) > MAX_PENDING_RESENDS:
            entry["messages"] = messages[-MAX_PENDING_RESENDS:]
        entry["timestamp"] = time.time() - NETWORK_RECOVERY_INTERVAL

async def process_network_recovery(bot, min_interval: float = NETWORK_RECOVERY_INTERVAL) -> None:
    async with network_recovery_lock:
        snapshot = {
            chat_id: {
                "timestamp": payload.get("timestamp", 0.0),
                "messages": list(payload.get("messages", [])),
            }
            for chat_id, payload in network_recovery_pending.items()
        }

    if not snapshot:
        return

    now = time.time()
    for chat_id, payload in snapshot.items():
        messages = payload.get("messages", [])
        timestamp = payload.get("timestamp", 0.0)

        if not messages:
            async with network_recovery_lock:
                network_recovery_pending.pop(chat_id, None)
            continue

        if now - timestamp < min_interval:
            continue

        remaining = []
        sent_count = 0
        failure = False

        for idx, (msg_text, msg_kwargs) in enumerate(messages):
            try:
                await bot.send_message(chat_id, msg_text, **msg_kwargs)
                sent_count += 1
            except RetryAfter as retry_error:
                delay = getattr(retry_error, "retry_after", min_interval)
                remaining = messages[idx:]
                async with network_recovery_lock:
                    network_recovery_pending[chat_id] = {
                        "timestamp": now + delay,
                        "messages": remaining,
                    }
                failure = True
                break
            except (NetworkError, asyncio.TimeoutError):
                remaining = messages[idx:]
                async with network_recovery_lock:
                    network_recovery_pending[chat_id] = {
                        "timestamp": now,
                        "messages": remaining,
                    }
                failure = True
                break
            except TelegramError:
                continue

        if failure:
            continue

        async with network_recovery_lock:
            network_recovery_pending.pop(chat_id, None)

        if sent_count:
            try:
                await bot.send_message(
                    chat_id,
                    f"✅ Connection restored. Delivered {sent_count} pending messages."
                )
            except TelegramError:
                pass

async def safe_reply(update: Update, text: str, retries: int = 3, base_delay: float = 2.0, **kwargs):
    chat_id = update.effective_chat.id
    kwargs_copy = dict(kwargs)
    last_error: Optional[Exception] = None
    last_recoverable = False

    for attempt in range(retries):
        try:
            return await update.message.reply_text(text, **kwargs)
        except RetryAfter as error:
            last_error = error
            last_recoverable = True
            delay = getattr(error, "retry_after", base_delay * (attempt + 1))
            await asyncio.sleep(delay)
        except (NetworkError, asyncio.TimeoutError) as error:
            last_error = error
            last_recoverable = True
            delay = base_delay * (attempt + 1)
            await asyncio.sleep(delay)
        except TelegramError as error:
            last_error = error
            last_recoverable = False
            break

    if last_recoverable:
        await mark_network_issue(chat_id, text, kwargs_copy)
        await process_network_recovery(update.get_bot())

    if last_error:
        logger.error(f"Failed to send message: {last_error}")
    return None

async def safe_send_document(bot, chat_id, **kwargs):
    document_obj = kwargs.get("document")
    for attempt in range(3):
        try:
            if document_obj and hasattr(document_obj, "seek"):
                document_obj.seek(0)
            return await bot.send_document(chat_id=chat_id, **kwargs)
        except RetryAfter as e:
            await asyncio.sleep(e.retry_after + 1)
        except (TimedOut, NetworkError):
            await asyncio.sleep(2 ** attempt)
        except TelegramError as e:
            logger.error(f"Telegram error sending document: {e}")
            break
    raise RuntimeError("Failed to send document after retries.")

async def send_document_from_path(bot, chat_id: int, path: Any, **kwargs) -> None:
    if not path.is_file():
        raise FileNotFoundError(f"File not found: {path}")

    filename = kwargs.pop("filename", path.name)
    def _open_file():
        return path.open("rb")

    file_handle = await asyncio.to_thread(_open_file)
    try:
        await safe_send_document(bot, chat_id=chat_id, document=file_handle, filename=filename, **kwargs)
    finally:
        try:
            file_handle.close()
        except Exception:
            pass
