import re
import random
import string
from datetime import datetime
from calendar import monthrange
from typing import Optional, Tuple
from config.settings import settings

def generate_unique_filename() -> str:
    return ''.join(random.choices(string.ascii_letters + string.digits, k=16)) + ".jpg"

def sanitize_filename(filename: str) -> str:
    cleaned = re.sub(r'[\/:*?"<>|]', '_', filename)
    reserved_names = {"CON", "PRN", "AUX", "NUL", "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9", "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9"}
    if cleaned.upper() in reserved_names:
        cleaned = f"_{cleaned}_"
    return cleaned[:150]

def is_digit(value: str) -> bool:
    return value.isdigit()

def is_valid_ticket_number(value: str) -> bool:
    return value.isdigit() and settings.MIN_TICKET_DIGITS <= len(value) <= settings.MAX_TICKET_DIGITS

def match_region_name(text: str) -> Optional[str]:
    cleaned = (text or "").strip().lower()
    for region in settings.REGION_TOPICS.keys():
        if region.lower() == cleaned:
            return region
    return None

def normalize_region_input(text: str) -> Optional[str]:
    if not text:
        return None
    cleaned = text.strip()
    if cleaned.startswith("🌍"):
        parts = cleaned.split(" ", 1)
        if len(parts) > 1:
            cleaned = parts[1]
    matched = match_region_name(cleaned)
    if matched:
        return matched
    return cleaned if cleaned in settings.REGION_TOPICS else None

from datetime import timedelta

def parse_date_str(date_text: str) -> Optional[datetime]:
    text = date_text.strip().lower()
    now = datetime.now()
    
    if text in ("сегодня", "today"):
        return now
    if text in ("вчера", "yesterday"):
        return now - timedelta(days=1)
        
    # Try formats
    formats = [
        "%d.%m.%Y", "%d/%m/%Y", "%d-%m-%Y",  # Full date
        "%d.%m", "%d/%m", "%d-%m"            # Date without year
    ]
    
    for fmt in formats:
        try:
            dt = datetime.strptime(text, fmt)
            # If year is missing (1900), replace with current year
            if dt.year == 1900:
                dt = dt.replace(year=now.year)
            return dt
        except ValueError:
            continue
            
    return None

def get_month_bounds(month_text: str) -> Optional[Tuple[datetime, datetime]]:
    try:
        month_date = datetime.strptime(month_text, "%m.%Y")
    except ValueError:
        return None
    last_day = monthrange(month_date.year, month_date.month)[1]
    start = month_date.replace(day=1)
    end = month_date.replace(day=last_day)
    return start, end

def ticket_digits_phrase() -> str:
    if settings.MIN_TICKET_DIGITS == settings.MAX_TICKET_DIGITS:
        return f"ровно {settings.MIN_TICKET_DIGITS} цифр"
    return f"от {settings.MIN_TICKET_DIGITS} до {settings.MAX_TICKET_DIGITS} цифр"

def format_progress(stage: str, progress_steps: dict, total_steps: int) -> str:
    step = progress_steps.get(stage)
    if not step:
        return ""
    return f"Шаг {step}/{total_steps}"
