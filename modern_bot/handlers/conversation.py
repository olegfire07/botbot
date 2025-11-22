from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, InputMediaPhoto
from telegram.ext import CallbackContext, ConversationHandler, CommandHandler, MessageHandler, filters
from modern_bot.config import (
    PROGRESS_STEPS, TOTAL_STEPS, MAX_PHOTOS, MAX_PHOTO_SIZE_MB, 
    PHOTO_REQUIREMENTS_MESSAGE, REGION_TOPICS, MAIN_GROUP_CHAT_ID
)
from modern_bot.utils.validators import is_digit, is_valid_ticket_number, normalize_region_input
from modern_bot.utils.files import generate_unique_filename, compress_image, is_image_too_large
from modern_bot.database.db import save_user_data, load_user_data, delete_user_data
from modern_bot.services.docx_gen import create_document
from modern_bot.services.excel import update_excel
from modern_bot.services.archive import archive_document
from modern_bot.handlers.common import safe_reply, send_document_from_path
from modern_bot.config import TEMP_PHOTOS_DIR
import logging
import json
from pathlib import Path

logger = logging.getLogger(__name__)

(DEPARTMENT, ISSUE_NUMBER, TICKET_NUMBER, DATE, REGION, PHOTO, DESCRIPTION, EVALUATION,
 MORE_PHOTO, CONFIRMATION, TESTING) = range(11)

def format_progress(stage: str) -> str:
    step = PROGRESS_STEPS.get(stage)
    return f"Step {step}/{TOTAL_STEPS}" if step else ""

async def start_conversation(update: Update, context: CallbackContext) -> int:
    user_id = update.message.from_user.id
    await delete_user_data(user_id)
    await save_user_data(user_id, {'photo_desc': []})
    
    await safe_reply(
        update,
        f"👋 Hello! Let's create a new conclusion.\n\n"
        f"🟡 {format_progress('department')}\nEnter Department Number:"
    )
    return DEPARTMENT

async def get_department(update: Update, context: CallbackContext) -> int:
    if not is_digit(update.message.text):
        await safe_reply(update, "Digits only please.")
        return DEPARTMENT
    
    user_id = update.message.from_user.id
    data = await load_user_data(user_id)
    data['department_number'] = update.message.text
    await save_user_data(user_id, data)
    
    await safe_reply(update, f"✅ Saved.\n\n🟡 {format_progress('issue')}\nEnter Issue Number:")
    return ISSUE_NUMBER

async def get_issue_number(update: Update, context: CallbackContext) -> int:
    if not is_digit(update.message.text):
        await safe_reply(update, "Digits only please.")
        return ISSUE_NUMBER
        
    user_id = update.message.from_user.id
    data = await load_user_data(user_id)
    data['issue_number'] = update.message.text
    await save_user_data(user_id, data)
    
    await safe_reply(update, f"✅ Saved.\n\n🟡 {format_progress('ticket')}\nEnter Ticket Number:")
    return TICKET_NUMBER

async def get_ticket_number(update: Update, context: CallbackContext) -> int:
    if not is_valid_ticket_number(update.message.text):
        await safe_reply(update, "Invalid ticket number format.")
        return TICKET_NUMBER
        
    user_id = update.message.from_user.id
    data = await load_user_data(user_id)
    data['ticket_number'] = update.message.text
    await save_user_data(user_id, data)
    
    await safe_reply(update, f"✅ Saved.\n\n🟡 {format_progress('date')}\nEnter Date (DD.MM.YYYY):")
    return DATE

async def get_date(update: Update, context: CallbackContext) -> int:
    # Simple validation, real validation in utils
    user_id = update.message.from_user.id
    data = await load_user_data(user_id)
    data['date'] = update.message.text
    await save_user_data(user_id, data)
    
    regions = [[f"🌍 {r}"] for r in REGION_TOPICS.keys()]
    markup = ReplyKeyboardMarkup(regions, one_time_keyboard=True, resize_keyboard=True)
    await safe_reply(update, f"✅ Saved.\n\n🟡 {format_progress('region')}\nSelect Region:", reply_markup=markup)
    return REGION

async def get_region(update: Update, context: CallbackContext) -> int:
    region = normalize_region_input(update.message.text)
    if not region:
        await safe_reply(update, "Please select a valid region.")
        return REGION
        
    user_id = update.message.from_user.id
    data = await load_user_data(user_id)
    data['region'] = region
    await save_user_data(user_id, data)
    
    await safe_reply(
        update, 
        f"✅ Saved.\n\n🟡 {format_progress('photo')}\nSend a photo.\n{PHOTO_REQUIREMENTS_MESSAGE}",
        reply_markup=ReplyKeyboardRemove()
    )
    return PHOTO

async def photo_handler(update: Update, context: CallbackContext) -> int:
    user_id = update.message.from_user.id
    photo_file = await update.message.photo[-1].get_file()
    
    TEMP_PHOTOS_DIR.mkdir(parents=True, exist_ok=True)
    unique_name = generate_unique_filename()
    orig_path = TEMP_PHOTOS_DIR / f"orig_{unique_name}"
    comp_path = TEMP_PHOTOS_DIR / unique_name
    
    await photo_file.download_to_drive(orig_path)
    compress_image(orig_path, comp_path)
    if orig_path.exists():
        orig_path.unlink()
        
    data = await load_user_data(user_id)
    data.setdefault('photo_desc', []).append({'photo': str(comp_path), 'description': '', 'evaluation': ''})
    await save_user_data(user_id, data)
    
    await safe_reply(update, f"✅ Photo received.\n\n✏️ Enter description:")
    return DESCRIPTION

async def description_handler(update: Update, context: CallbackContext) -> int:
    user_id = update.message.from_user.id
    data = await load_user_data(user_id)
    if data.get('photo_desc'):
        data['photo_desc'][-1]['description'] = update.message.text
    await save_user_data(user_id, data)
    
    await safe_reply(update, f"✅ Saved.\n\n💰 Enter evaluation (digits):")
    return EVALUATION

async def evaluation_handler(update: Update, context: CallbackContext) -> int:
    if not is_digit(update.message.text):
        await safe_reply(update, "Digits only.")
        return EVALUATION
        
    user_id = update.message.from_user.id
    data = await load_user_data(user_id)
    if data.get('photo_desc'):
        data['photo_desc'][-1]['evaluation'] = update.message.text
    await save_user_data(user_id, data)
    
    markup = ReplyKeyboardMarkup([["Yes", "No"]], one_time_keyboard=True, resize_keyboard=True)
    await safe_reply(update, "Add another photo?", reply_markup=markup)
    return MORE_PHOTO

async def more_photo_handler(update: Update, context: CallbackContext) -> int:
    if "yes" in update.message.text.lower():
        await safe_reply(update, "Send next photo.", reply_markup=ReplyKeyboardRemove())
        return PHOTO
    
    markup = ReplyKeyboardMarkup([["Test", "Final"]], one_time_keyboard=True, resize_keyboard=True)
    await safe_reply(update, "Select mode:", reply_markup=markup)
    return TESTING

async def testing_handler(update: Update, context: CallbackContext) -> int:
    user_id = update.message.from_user.id
    mode = update.message.text.lower()
    
    await safe_reply(update, "Generating document...", reply_markup=ReplyKeyboardRemove())
    
    try:
        path = await create_document(user_id, update.message.from_user.full_name)
        await send_document_from_path(context.bot, user_id, path)
        
        if "final" in mode:
            data = await load_user_data(user_id)
            region = data.get('region')
            topic_id = REGION_TOPICS.get(region)
            if topic_id:
                await send_document_from_path(context.bot, MAIN_GROUP_CHAT_ID, path, message_thread_id=topic_id)
                await update_excel(data)
                await archive_document(path, data)
                await safe_reply(update, "✅ Sent to group.")
            else:
                await safe_reply(update, "⚠️ Region topic not found, not sent to group.")
                
        if path.exists():
            path.unlink()
            
    except Exception as e:
        logger.error(f"Error: {e}")
        await safe_reply(update, "Error generating document.")
        
    return ConversationHandler.END

async def cancel_handler(update: Update, context: CallbackContext) -> int:
    await safe_reply(update, "Cancelled.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

def get_conversation_handler():
    return ConversationHandler(
        entry_points=[CommandHandler("start_chat", start_conversation)],
        states={
            DEPARTMENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_department)],
            ISSUE_NUMBER: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_issue_number)],
            TICKET_NUMBER: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_ticket_number)],
            DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_date)],
            REGION: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_region)],
            PHOTO: [MessageHandler(filters.PHOTO, photo_handler)],
            DESCRIPTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, description_handler)],
            EVALUATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, evaluation_handler)],
            MORE_PHOTO: [MessageHandler(filters.TEXT & ~filters.COMMAND, more_photo_handler)],
            TESTING: [MessageHandler(filters.TEXT & ~filters.COMMAND, testing_handler)],
        },
        fallbacks=[CommandHandler("cancel", cancel_handler)]
    )
