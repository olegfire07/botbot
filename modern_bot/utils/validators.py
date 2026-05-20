from datetime import datetime, timedelta
from calendar import monthrange
from typing import Optional, Tuple
from modern_bot.config import REGION_TOPICS, MIN_TICKET_DIGITS, MAX_TICKET_DIGITS

def is_digit(value: str) -> bool:
    return value.isdigit()

def is_valid_ticket_number(value: str) -> bool:
    return value.isdigit() and MIN_TICKET_DIGITS <= len(value) <= MAX_TICKET_DIGITS

def match_region_name(text: str) -> Optional[str]:
    cleaned = (text or "").strip().lower()
    for region in REGION_TOPICS.keys():
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
    return cleaned if cleaned in REGION_TOPICS else None

def parse_date_str(date_text: str) -> Optional[datetime]:
    try:
        return datetime.strptime(date_text, "%d.%m.%Y")
    except (ValueError, TypeError):
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
