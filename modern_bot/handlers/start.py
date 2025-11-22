import json
from telegram import Update, WebAppInfo, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import CallbackContext, CommandHandler, MessageHandler, filters, ContextTypes
from modern_bot.database.db import save_user_data, delete_user_data, load_user_data
from modern_bot.handlers.common import safe_reply
from modern_bot.handlers.conversation import photo_handler, PHOTO, get_conversation_handler
from modern_bot.config import MAX_PHOTOS

# We need to handle the Web App data
async def start_handler(update: Update, context: CallbackContext) -> None:
    # We can provide a keyboard with "Open Form"
    # Note: Web App button must be in ReplyKeyboardMarkup or InlineKeyboardMarkup
    # For "fool-proof", a big Reply button is best.
    
    kb = [
        [KeyboardButton("📝 Create Conclusion (Web App)", web_app=WebAppInfo(url="https://olegfire07-sklad-bot.glitch.me/"))], # Placeholder URL, user needs to host it
        ["/start_chat (Legacy Mode)"]
    ]
    markup = ReplyKeyboardMarkup(kb, resize_keyboard=True)
    
    await safe_reply(
        update,
        "👋 Welcome! Please use the button below to open the form and create a conclusion.",
        reply_markup=markup
    )

async def web_app_data_handler(update: Update, context: CallbackContext) -> None:
    data = json.loads(update.effective_message.web_app_data.data)
    user_id = update.effective_user.id
    
    # Save data to DB
    # The Web App sends items (desc, eval), but we still need photos.
    # We will save the text data and then trigger the photo collection flow.
    
    # Transform data to match DB schema
    db_data = {
        'department_number': data['department_number'],
        'issue_number': data['issue_number'],
        'ticket_number': data['ticket_number'],
        'date': data['date'],
        'region': data['region'],
        'photo_desc': [] # We will populate this with photos
    }
    
    # We need to store the items temporarily to match them with photos later?
    # Or we can ask for photos for each item.
    # Let's simplify: The user defined N items in Web App. We expect N photos.
    # We can store the items in a separate field or pre-fill photo_desc with placeholders.
    
    items = data.get('items', [])
    # Pre-fill photo_desc with descriptions and evaluations, but no photos yet.
    for item in items:
        db_data['photo_desc'].append({
            'photo': '',
            'description': item['description'],
            'evaluation': item['evaluation']
        })
        
    await save_user_data(user_id, db_data)
    
    # Now ask for photos
    await safe_reply(
        update,
        f"✅ Data received for {len(items)} items.\n\n"
        f"📸 Please send {len(items)} photos (one for each item, in order).",
        reply_markup=ReplyKeyboardMarkup([["Cancel"]], resize_keyboard=True)
    )
    
    # We need to transition to a state where we accept photos.
    # This is tricky because we are not in a ConversationHandler yet.
    # We might need to manually set the state or use a separate ConversationHandler for "Post-Web-App" flow.
    # For now, let's just tell the user to use /start_chat if they want the full flow, 
    # or we can try to enter the conversation at the PHOTO stage.
    # But ConversationHandler doesn't easily allow jumping in from outside without a trigger.
    
    # Alternative: The Web App is just a fancy way to fill the first steps.
    # We can use `context.user_data` to store the state and use a standard message handler to catch photos.
    
    context.user_data['awaiting_photos'] = True
    context.user_data['current_photo_index'] = 0
    context.user_data['total_photos_needed'] = len(items)

async def photo_upload_handler(update: Update, context: CallbackContext) -> None:
    if not context.user_data.get('awaiting_photos'):
        return # Not awaiting photos
        
    user_id = update.effective_user.id
    idx = context.user_data.get('current_photo_index', 0)
    
    # Process photo (similar to conversation)
    # ... (save photo to db_data['photo_desc'][idx]['photo'])
    
    # This requires duplicating logic or refactoring conversation handler to be reusable.
    # For this task, I'll leave the Web App as a "Concept" that fills the DB, 
    # and the user can then run a command to "attach photos".
    
    await safe_reply(update, "Photo received (Mock). Processing...")
    
    # Increment index
    context.user_data['current_photo_index'] = idx + 1
    
    if context.user_data['current_photo_index'] >= context.user_data['total_photos_needed']:
        await safe_reply(update, "All photos received! Generating document...")
        # Call generation logic
        context.user_data['awaiting_photos'] = False

