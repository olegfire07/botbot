import logging
from pathlib import Path
from telegram import Update
from telegram.ext import CallbackContext
from modern_bot.config import MAIN_GROUP_CHAT_ID, TEMP_PHOTOS_DIR
from modern_bot.utils.files import compress_image

logger = logging.getLogger(__name__)

async def dump_handler(update: Update, context: CallbackContext) -> None:
    """
    Intercepts photos sent to the main group with a UUID caption.
    Downloads the photo, saves it with the UUID as filename, and deletes the message.
    """
    logger.info(f"Dump handler triggered! Chat ID: {update.effective_chat.id}")
    
    # Only process messages in the main group
    if update.effective_chat.id != MAIN_GROUP_CHAT_ID:
        logger.info(f"Ignoring message from chat {update.effective_chat.id} (expected {MAIN_GROUP_CHAT_ID})")
        return

    # Check if it's a photo and has a caption starting with UUID:
    if not update.message.photo:
        logger.info("No photo in message")
        return
        
    if not update.message.caption:
        logger.info("No caption in message")
        return

    caption = update.message.caption.strip()
    logger.info(f"Processing caption: {caption}")
    
    if "UUID:" not in caption:
        logger.info("Caption does not contain UUID:")
        return

    try:
        uuid_code = caption.split("UUID:")[1].strip()
    except IndexError:
        logger.warning(f"Malformed UUID caption: {caption}")
        return

    if not uuid_code:
        return

    try:
        # Download the photo
        photo_file = await update.message.photo[-1].get_file()
        
        TEMP_PHOTOS_DIR.mkdir(parents=True, exist_ok=True)
        
        # Save directly with UUID as filename (we'll compress it later or now)
        # Let's save as .jpg
        file_path = TEMP_PHOTOS_DIR / f"{uuid_code}.jpg"
        
        # Download to a temp path first to compress
        temp_path = TEMP_PHOTOS_DIR / f"temp_{uuid_code}.jpg"
        await photo_file.download_to_drive(temp_path)
        
        # Compress and rename/move
        compress_image(temp_path, file_path)
        
        if temp_path.exists():
            temp_path.unlink()
            
        logger.info(f"✅ Intercepted and saved photo for UUID {uuid_code} at {file_path}")

        # Delete the message to avoid spam
        try:
            await update.message.delete()
            logger.info("Deleted dump message")
        except Exception as e:
            logger.warning(f"Could not delete dump message: {e}")

    except Exception as e:
        logger.error(f"Error in dump_handler: {e}", exc_info=True)
