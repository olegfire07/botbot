import os
from pathlib import Path
from typing import Dict, List

from dotenv import load_dotenv

# Load env vars from .env file
env_path = Path(__file__).parent.parent / '.env'
load_dotenv(dotenv_path=env_path)

# --- BOT SETTINGS ---
BOT_TOKEN_ENV_VAR = "BOT_TOKEN"

# --- IMGBB SETTINGS ---
# Support IMGBB_KEY (documented).
IMGBB_KEY: str = os.getenv("IMGBB_KEY", "").strip()

# Admin IDs (load from environment for security)
ADMIN_IDS = [
    int(id.strip()) 
    for id in os.getenv("ADMIN_IDS", "2064900,636601018").split(",") 
    if id.strip()
]

# Super Admin ID (Protected from removal)
def _load_super_admin_id(default_id: int) -> int:
    value = os.getenv("SUPER_ADMIN_ID", "").strip()
    if not value:
        return default_id
    try:
        return int(value)
    except ValueError:
        return default_id

SUPER_ADMIN_ID = _load_super_admin_id(2064900)

# --- API SETTINGS ---
API_ENABLED: bool = os.getenv("API_ENABLED", "true").lower() == "true"
API_PORT: int = int(os.getenv("API_PORT", "8080"))
API_BIND_HOST: str = os.getenv("API_BIND_HOST", "0.0.0.0")
API_AUTH_TOKEN: str = os.getenv("API_AUTH_TOKEN", "").strip()
API_MAX_REQUEST_SIZE_MB: int = int(os.getenv("API_MAX_REQUEST_SIZE_MB", "2"))

def load_bot_token():
    """
    Loads the bot token from environment variables.
    Token MUST be set in .env file — hardcoded fallback removed for security.
    """
    token = os.getenv(BOT_TOKEN_ENV_VAR, "").strip()
    if not token:
        raise RuntimeError(
            "❌ BOT_TOKEN не найден! Укажите токен бота в файле .env:\n"
            "   BOT_TOKEN=ваш_токен_от_BotFather"
        )
    return token

MAIN_GROUP_CHAT_ID: int = -1002381542769
DEFAULT_ADMIN_IDS: List[int] = [
    int(id.strip()) 
    for id in os.getenv("DEFAULT_ADMIN_IDS", "2064900,7511144435,960665399,478023829,912447830,465479436,625352555,466509784,649764051").split(",") 
    if id.strip()
]
if SUPER_ADMIN_ID not in DEFAULT_ADMIN_IDS:
    DEFAULT_ADMIN_IDS.insert(0, SUPER_ADMIN_ID)

REGION_TOPICS: Dict[str, int] = {
    "Санкт-Петербург": 11, "Свердловская область": 8, "Челябинская область": 6,
    "Екатеринбург": 4, "Башкирия": 12, "Тюмень": 13, "ХМАО-Югра": 15,
    "Нижний Новгород": 9, "Ростовская область": 17, "Челябинск": 2,
    "Магнитогорск": 7, "Курган": 16, "Краснодарский край": 14,
}

# Regional Groups logic removed as per user feedback. All reports go to MAIN_GROUP_CHAT_ID.


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
PHOTO_STORE_MODE: str = os.getenv("PHOTO_STORE_MODE", "local").strip().lower()
MIN_TICKET_DIGITS: int = 11
MAX_TICKET_DIGITS: int = 11
PREVIEW_MAX_ITEMS: int = 2
NETWORK_RECOVERY_INTERVAL: float = 45.0
MAX_PENDING_RESENDS: int = 20
MENU_BUTTON_LABEL = "/menu 📋"
ARCHIVE_RETENTION_DAYS: int = 90
DATA_RETENTION_DAYS: int = int(os.getenv("DATA_RETENTION_DAYS", str(ARCHIVE_RETENTION_DAYS)))
# Chat ID to dump photos for file_id generation (using main group or specific channel)
PHOTO_STORAGE_CHAT_ID: int = MAIN_GROUP_CHAT_ID

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
