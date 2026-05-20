import logging
import os
from pathlib import Path
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, CopyTextButton
from telegram.ext import CallbackContext, ConversationHandler, CallbackQueryHandler, MessageHandler, filters
from modern_bot.handlers.common import safe_reply, send_document_from_path
from modern_bot.services.excel import read_excel_data
from modern_bot.handlers.admin import is_admin
import openpyxl

logger = logging.getLogger(__name__)

WAITING_FOR_FILE, WAITING_FOR_PERIOD, WAITING_FOR_CUSTOM_DATES = range(3)

async def start_reconciliation(update: Update, context: CallbackContext) -> int:
    """Start the reconciliation process."""
    query = update.callback_query
    if query:
        await query.answer()
    
    if not is_admin(update.effective_user.id):
        await safe_reply(update, "❌ Доступ запрещен.")
        return ConversationHandler.END

    await safe_reply(
        update, 
        "🔍 <b>Сверка билетов</b>\n\n"
        "Пожалуйста, отправьте файл со списком билетов.\n"
        "Поддерживаемые форматы:\n"
        "📄 <b>.txt</b> (один номер билета на строку)\n"
        "📊 <b>.xlsx</b> (номера билетов должны быть в первом столбце)\n\n"
        "Отправьте /cancel для отмены.",
        parse_mode="HTML"
    )
    return WAITING_FOR_FILE

from modern_bot.utils.date_helper import DateFilter

async def handle_reconciliation_file(update: Update, context: CallbackContext) -> int:
    """Handle the uploaded file and ask for period."""
    user = update.effective_user
    document = update.message.document
    
    if not document:
        await safe_reply(update, "❌ Пожалуйста, отправьте файл (документ).")
        return WAITING_FOR_FILE

    file_name = document.file_name
    file_ext = os.path.splitext(file_name)[1].lower()
    
    if file_ext not in ['.txt', '.xlsx']:
        await safe_reply(update, "❌ Поддерживаются только файлы .txt и .xlsx")
        return WAITING_FOR_FILE

    # Check file size (max 10MB)
    if document.file_size and document.file_size > 10 * 1024 * 1024:
        await safe_reply(update, "❌ Файл слишком большой. Максимальный размер 10 МБ.")
        return WAITING_FOR_FILE

    await safe_reply(update, "⏳ Обрабатываю файл...")

    try:
        # Download file
        new_file = await context.bot.get_file(document.file_id)
        file_path = Path(f"temp_reconcile_{user.id}_{file_name}")
        await new_file.download_to_drive(file_path)
        
        uploaded_tickets = set()
        
        # Parse file
        if file_ext == '.txt':
            with open(file_path, 'r', encoding='utf-8') as f:
                for line in f:
                    ticket = line.strip()
                    clean_ticket = "".join(filter(str.isdigit, ticket))
                    if clean_ticket:
                        uploaded_tickets.add(clean_ticket)
                        
        elif file_ext == '.xlsx':
            try:
                wb = openpyxl.load_workbook(file_path)
                ws = wb.active
                for row in ws.iter_rows(values_only=True):
                    if row and row[0]:
                        ticket = str(row[0]).strip()
                        clean_ticket = "".join(filter(str.isdigit, ticket))
                        if clean_ticket:
                            uploaded_tickets.add(clean_ticket)
                wb.close()
            except Exception as e:
                logger.error(f"Excel parsing error: {e}")
                await safe_reply(update, "❌ Ошибка чтения Excel файла. Убедитесь, что файл не поврежден.")
                if file_path.exists():
                    file_path.unlink()
                return ConversationHandler.END
            
        # Cleanup uploaded file
        if file_path.exists():
            file_path.unlink()
            
        if not uploaded_tickets:
            await safe_reply(update, "❌ Не удалось найти корректные номера билетов в файле.")
            return ConversationHandler.END
            
        # Save tickets to context
        context.user_data['reconcile_tickets'] = uploaded_tickets
        
        # Ask for period using DateFilter
        keyboard = DateFilter.get_keyboard("period")
        keyboard.append([InlineKeyboardButton("◀️ Отмена", callback_data="cancel_reconcile", style='danger')]) # Add cancel button explicitly if needed or rely on conversation exit
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await safe_reply(
            update, 
            f"✅ Файл принят. Найдено уникальных билетов: {len(uploaded_tickets)}\n\n"
            "Выберите период для сверки с базой бота:",
            reply_markup=reply_markup
        )
        return WAITING_FOR_PERIOD

    except Exception as e:
        logger.error(f"Error in reconciliation file processing: {e}", exc_info=True)
        await safe_reply(update, "❌ Произошла ошибка при обработке файла.")
        return ConversationHandler.END

async def handle_period_selection(update: Update, context: CallbackContext) -> int:
    """Handle standard period selection or prompt for custom dates."""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    # Expected format: period|PRESET
    
    if "|" not in data:
        # Fallback for old buttons if any
        return ConversationHandler.END
        
    _, selection = data.split("|", 1)
    
    if selection == DateFilter.PRESET_CUSTOM:
        await query.edit_message_text(
            "✏️ <b>Введите период для сверки</b>\n\n"
            "Формат: ДД.ММ.ГГГГ - ДД.ММ.ГГГГ\n"
            "Пример: <code>01.11.2025 - 15.11.2025</code>",
            parse_mode="HTML"
        )
        return WAITING_FOR_CUSTOM_DATES
    
    start_date, end_date, period_name = DateFilter.parse_selection(selection)
    
    if not start_date:
        await safe_reply(update, "❌ Ошибка выбора периода.")
        return ConversationHandler.END
        
    await query.edit_message_text(f"⏳ Сверяю данные ({period_name})...")
    await _perform_reconciliation(update, context, start_date, end_date, period_name)
    return ConversationHandler.END

async def handle_custom_dates(update: Update, context: CallbackContext) -> int:
    """Handle custom date range input."""
    text = update.message.text.strip()
    
    start_date, end_date = DateFilter.parse_custom_range(text)
    
    if not start_date:
        await safe_reply(
            update, 
            "❌ Неверный формат даты.\n"
            "Используйте формат: ДД.ММ.ГГГГ - ДД.ММ.ГГГГ\n"
            "Пример: 01.11.2025 - 15.11.2025"
        )
        return WAITING_FOR_CUSTOM_DATES
        
    period_name = f"{start_date.strftime('%d.%m.%Y')} - {end_date.strftime('%d.%m.%Y')}"
    
    await safe_reply(update, f"⏳ Сверяю данные ({period_name})...")
    await _perform_reconciliation(update, context, start_date, end_date, period_name)
    return ConversationHandler.END

async def _perform_reconciliation(update: Update, context: CallbackContext, start_date, end_date, period_name):
    """Internal function to perform the reconciliation logic."""
    uploaded_tickets = context.user_data.get('reconcile_tickets', set())
    user = update.effective_user
    
    try:
        # Get existing tickets from bot database (Excel)
        existing_rows = await read_excel_data()
        existing_tickets = set()
        
        # Filter rows
        for row in existing_rows:
            # Row structure: [ticket, issue, dept, date, region, ...]
            # Date is at index 3
            if not row or len(row) < 4:
                continue
                
            ticket_val = str(row[0]).strip() if row[0] else ""
            date_val = str(row[3]).strip() if row[3] else ""
            
            clean_ticket = "".join(filter(str.isdigit, ticket_val))
            if not clean_ticket:
                continue
                
            # Date check
            if start_date and end_date:
                try:
                    row_date = datetime.strptime(date_val, "%d.%m.%Y")
                    if not (start_date <= row_date <= end_date):
                        continue # Skip if outside range
                except ValueError:
                    continue # Skip invalid dates if filtering is on
            
            existing_tickets.add(clean_ticket)
                
        # Find missing
        missing_tickets = uploaded_tickets - existing_tickets
        
        report_text = (
            f"📊 <b>Результаты сверки ({period_name})</b>\n\n"
            f"📥 Загружено билетов: {len(uploaded_tickets)}\n"
            f"✅ Найдено в базе за период: {len(uploaded_tickets) - len(missing_tickets)}\n"
            f"❌ <b>Отсутствует заключений: {len(missing_tickets)}</b>\n"
        )
        
        if not missing_tickets:
            report_text += "\n🎉 Все загруженные билеты имеют заключения за выбранный период!"
            await safe_reply(update, report_text, parse_mode="HTML")
        else:
            # Создаем кнопку копирования всех отсутствующих номеров
            missing_text = "\n".join(sorted(missing_tickets))
            copy_keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("📋 Скопировать отсутствующие номера", copy_text=CopyTextButton(text=missing_text))]
            ])
            
            if len(missing_tickets) <= 20:
                report_text += "\n<b>Список отсутствующих:</b>\n" + "\n".join(sorted(missing_tickets))
                await safe_reply(update, report_text, parse_mode="HTML", reply_markup=copy_keyboard)
            else:
                # Create report file
                report_file = Path(f"missing_tickets_{user.id}.txt")
                with open(report_file, 'w', encoding='utf-8') as f:
                    f.write(f"Список билетов, по которым отсутствуют заключения ({period_name}):\n")
                    for t in sorted(missing_tickets):
                        f.write(f"{t}\n")
                
                await safe_reply(update, report_text, parse_mode="HTML", reply_markup=copy_keyboard)
                await send_document_from_path(context.bot, user.id, report_file, caption="📄 Список отсутствующих билетов")
                
                if report_file.exists():
                    report_file.unlink()

    except Exception as e:
        logger.error(f"Error in reconciliation comparison: {e}", exc_info=True)
        await safe_reply(update, "❌ Произошла ошибка при сверке.")
        
    return ConversationHandler.END

async def cancel_reconciliation(update: Update, context: CallbackContext) -> int:
    """Cancel the reconciliation process."""
    await safe_reply(update, "❌ Сверка отменена.")
    return ConversationHandler.END
