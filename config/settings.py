import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class Settings:
    # Bot Configuration
    BOT_TOKEN = os.getenv("BOT_TOKEN", "7514668293:AAHcxAooMsd1oDeoHOWkwbnTUD0BPUWePOY")
    
    # Chat IDs
    MAIN_GROUP_CHAT_ID = int(os.getenv("MAIN_GROUP_CHAT_ID", "-1002381542769"))
    DEFAULT_ADMIN_IDS = [int(x) for x in os.getenv("DEFAULT_ADMIN_IDS", "2064900").split(",")]

    # Paths
    BASE_DIR = Path(__file__).parent.parent
    TEMPLATE_PATH = BASE_DIR / "template.docx"
    TEMP_PHOTOS_DIR = BASE_DIR / "photos"
    DOCS_DIR = BASE_DIR / "documents"
    ARCHIVE_DIR = BASE_DIR / "documents_archive"
    ARCHIVE_INDEX_FILE = ARCHIVE_DIR / "index.json"
    ADMIN_FILE = BASE_DIR / "config" / "admins.json"
    DATABASE_FILE = BASE_DIR / "user_data.db"
    EXCEL_FILE = BASE_DIR / "conclusions.xlsx"

    # Constants
    MAX_PHOTOS = 30
    MAX_PHOTO_SIZE_MB = 5
    MIN_TICKET_DIGITS = 11
    MAX_TICKET_DIGITS = 11
    PREVIEW_MAX_ITEMS = 2
    NETWORK_RECOVERY_INTERVAL = 45.0
    MAX_PENDING_RESENDS = 20
    
    # Region Configuration
    REGION_TOPICS = {
        "Санкт-Петербург": 11, "Свердловская область": 8, "Челябинская область": 6,
        "Екатеринбург": 4, "Башкирия": 12, "Тюмень": 13, "ХМАО-Югра": 15,
        "Нижний Новгород": 9, "Ростовская область": 17, "Челябинск": 2,
        "Магнитогорск": 7, "Курган": 16, "Краснодарский край": 14,
    }

    EXCEL_HEADERS = ["Ticket Number", "Conclusion Number", "Department Number", "Date", "Region", "Item Number", "Description", "Evaluation"]

settings = Settings()
