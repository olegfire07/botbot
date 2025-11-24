import os
from pathlib import Path
from typing import Dict, List

from dotenv import load_dotenv

# Load env vars from .env file
load_dotenv()

# --- BOT SETTINGS ---
BOT_TOKEN_ENV_VAR = "BOT_TOKEN"

# Admin IDs
ADMIN_IDS = [2064900, 636601018]  # Super admins

# --- API SETTINGS ---
API_ENABLED: bool = os.getenv("API_ENABLED", "true").lower() == "true"
API_PORT: int = int(os.getenv("API_PORT", "8080"))
API_BIND_HOST: str = os.getenv("API_BIND_HOST", "127.0.0.1")
API_AUTH_TOKEN: str = os.getenv("API_AUTH_TOKEN", "").strip()
API_MAX_REQUEST_SIZE_MB: int = int(os.getenv("API_MAX_REQUEST_SIZE_MB", "2"))

def load_bot_token():
    """
    Loads the bot token from environment variables.
    Raises ValueError if token is not found.
    """
    token = os.getenv(BOT_TOKEN_ENV_VAR, "").strip()
    if not token:
        raise ValueError(f"Bot token not found! Please set {BOT_TOKEN_ENV_VAR} in .env file.")
    return token

MAIN_GROUP_CHAT_ID: int = -1002381542769
DEFAULT_ADMIN_IDS: List[int] = [2064900]

REGION_TOPICS: Dict[str, int] = {
    "Санкт-Петербург": 11, "Свердловская область": 8, "Челябинская область": 6,
    "Екатеринбург": 4, "Башкирия": 12, "Тюмень": 13, "ХМАО-Югра": 15,
    "Нижний Новгород": 9, "Ростовская область": 17, "Челябинск": 2,
    "Магнитогорск": 7, "Курган": 16, "Краснодарский край": 14,
}

# --- PATHS ---
BASE_DIR = Path(__file__).parent.parent
TEMPLATE_PATH = BASE_DIR / "template.docx"
TEMP_PHOTOS_DIR = BASE_DIR / "photos"
DOCS_DIR = BASE_DIR / "documents"
ARCHIVE_DIR = BASE_DIR / "documents_archive"
ARCHIVE_INDEX_FILE = ARCHIVE_DIR / "index.json"
ADMIN_FILE = BASE_DIR / "config" / "admins.json"
DATABASE_FILE = BASE_DIR / "user_data.db"
EXCEL_FILE = BASE_DIR / "conclusions.xlsx"

# --- CONSTANTS ---
MAX_PHOTOS: int = 30
MAX_PHOTO_SIZE_MB: int = 5
MIN_TICKET_DIGITS: int = 11
MAX_TICKET_DIGITS: int = 11
PREVIEW_MAX_ITEMS: int = 2
NETWORK_RECOVERY_INTERVAL: float = 45.0
MAX_PENDING_RESENDS: int = 20
MENU_BUTTON_LABEL = "/menu 📋"

PHOTO_REQUIREMENTS_MESSAGE = (
    "Требования к фото:\n"
    "• Формат JPG/PNG\n"
    f"• Размер до {MAX_PHOTO_SIZE_MB} МБ\n"
    "• Минимальное разрешение 800×600"
)

EXCEL_HEADERS = [
    "Ticket Number", "Conclusion Number", "Department Number", 
    "Date", "Region", "Item Number", "Description", "Evaluation", "User"
]

# --- PROGRESS STEPS (Legacy Chat Flow) ---
PROGRESS_STEPS: Dict[str, int] = {
    "department": 1,
    "issue": 2,
    "ticket": 3,
    "date": 4,
    "region": 5,
    "photo": 6,
    "description": 7,
    "evaluation": 8,
    "summary": 9,
    "mode": 10,
}
TOTAL_STEPS: int = max(PROGRESS_STEPS.values())
