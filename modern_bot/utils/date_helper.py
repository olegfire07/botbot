from datetime import datetime, timedelta
from typing import Tuple, Optional
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

class DateFilter:
    """Helper for flexible date selection."""
    
    PRESET_TODAY = "today"
    PRESET_YESTERDAY = "yesterday"
    PRESET_WEEK = "week"
    PRESET_MONTH = "month"
    PRESET_LAST_MONTH = "last_month"
    PRESET_CUSTOM = "custom"
    
    @staticmethod
    def get_keyboard(prefix: str) -> list[list[InlineKeyboardButton]]:
        """Returns keyboard list with date presets."""
        keyboard = [
            [
                InlineKeyboardButton("📅 Сегодня", callback_data=f"{prefix}|{DateFilter.PRESET_TODAY}"),
                InlineKeyboardButton("⏮ Вчера", callback_data=f"{prefix}|{DateFilter.PRESET_YESTERDAY}")
            ],
            [
                InlineKeyboardButton("🗓 Эта неделя", callback_data=f"{prefix}|{DateFilter.PRESET_WEEK}"),
                InlineKeyboardButton("📆 Этот месяц", callback_data=f"{prefix}|{DateFilter.PRESET_MONTH}")
            ],
            [
                InlineKeyboardButton("🗂 Прошлый месяц", callback_data=f"{prefix}|{DateFilter.PRESET_LAST_MONTH}")
            ],
            [
                InlineKeyboardButton("✏️ Ввести вручную (ДД.ММ.ГГГГ - ДД.ММ.ГГГГ)", callback_data=f"{prefix}|{DateFilter.PRESET_CUSTOM}")
            ]
        ]
        return keyboard

    @staticmethod
    def parse_selection(selection: str) -> Tuple[Optional[datetime], Optional[datetime], str]:
        """
        Parses preset selection into start and end dates.
        Returns (start_date, end_date, description).
        """
        now = datetime.now()
        today = now.replace(hour=0, minute=0, second=0, microsecond=0)
        
        if selection == DateFilter.PRESET_TODAY:
            return today, now, "Сегодня"
            
        elif selection == DateFilter.PRESET_YESTERDAY:
            yesterday = today - timedelta(days=1)
            end_yesterday = yesterday.replace(hour=23, minute=59, second=59)
            return yesterday, end_yesterday, "Вчера"
            
        elif selection == DateFilter.PRESET_WEEK:
            start = today - timedelta(days=today.weekday())  # Monday
            return start, now, "Эта неделя"
            
        elif selection == DateFilter.PRESET_MONTH:
            start = today.replace(day=1)
            return start, now, "Этот месяц"
            
        elif selection == DateFilter.PRESET_LAST_MONTH:
            first_this_month = today.replace(day=1)
            last_month_end = first_this_month - timedelta(seconds=1)
            last_month_start = last_month_end.replace(day=1, hour=0, minute=0, second=0)
            return last_month_start, last_month_end, "Прошлый месяц"
            
        return None, None, "Custom"

    @staticmethod
    def parse_custom_range(text: str) -> Tuple[Optional[datetime], Optional[datetime]]:
        """Parses custom date range string 'DD.MM.YYYY - DD.MM.YYYY'."""
        try:
            parts = text.split('-')
            if len(parts) != 2:
                return None, None
                
            start_str = parts[0].strip()
            end_str = parts[1].strip()
            
            start = datetime.strptime(start_str, "%d.%m.%Y")
            end = datetime.strptime(end_str, "%d.%m.%Y").replace(hour=23, minute=59, second=59)
            
            if start > end:
                start, end = end, start
                
            return start, end
        except ValueError:
            return None, None

    @staticmethod
    def process_callback(data: str) -> Tuple[Optional[datetime], Optional[datetime]]:
        """
        Extracts selection from callback data and parses it.
        Expected format: prefix|selection
        Returns (start_date, end_date).
        """
        if "|" not in data:
            return None, None
            
        _, selection = data.split("|", 1)
        
        # Handle custom selection separately if needed, but parse_selection handles presets
        # If selection is 'custom', parse_selection returns (None, None, "Custom")
        
        start, end, _ = DateFilter.parse_selection(selection)
        return start, end
