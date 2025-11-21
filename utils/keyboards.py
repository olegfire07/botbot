from typing import List
from telegram import ReplyKeyboardMarkup, KeyboardButton

MENU_BUTTON_LABEL = "/menu 📋"
BACK_BUTTON_LABEL = "⬅️ Назад"

def ensure_menu_button(rows: List[List[str]]) -> List[List[str]]:
    has_menu = any(MENU_BUTTON_LABEL in row for row in rows)
    new_rows = [list(row) for row in rows]
    if not has_menu:
        new_rows.append([MENU_BUTTON_LABEL])
    return new_rows

def ensure_back_button(rows: List[List[str]]) -> List[List[str]]:
    has_back = any(BACK_BUTTON_LABEL in row for row in rows)
    new_rows = [list(row) for row in rows]
    
    if not has_back:
        if new_rows and MENU_BUTTON_LABEL in new_rows[-1]:
             new_rows.insert(len(new_rows)-1, [BACK_BUTTON_LABEL])
        else:
             new_rows.append([BACK_BUTTON_LABEL])
    return new_rows

def build_keyboard(rows: List[List[str]], one_time: bool = False) -> ReplyKeyboardMarkup:
    button_rows = [[KeyboardButton(text=label) for label in row] for row in rows]
    return ReplyKeyboardMarkup(button_rows, one_time_keyboard=one_time, resize_keyboard=False)

def build_keyboard_with_menu(rows: List[List[str]], one_time: bool = False, add_back: bool = False) -> ReplyKeyboardMarkup:
    rows = ensure_menu_button(rows)
    if add_back:
        rows = ensure_back_button(rows)
    return build_keyboard(rows, one_time=one_time)

def build_region_filter_keyboard(regions: dict, include_all: bool = True) -> ReplyKeyboardMarkup:
    rows: List[List[str]] = []
    if include_all:
        rows.append(["🌐 Все регионы"])
    rows.extend([[f"🌍 {region}"] for region in regions.keys()])
    rows.append(["❌ Отмена"])
    return build_keyboard_with_menu(rows, one_time=True)

from telegram import ReplyKeyboardMarkup, KeyboardButton, WebAppInfo

# ... (existing constants)

def build_main_menu(user_id: int, admin_ids: List[int] = None) -> ReplyKeyboardMarkup:
    # Replace this URL with your actual GitHub Pages URL after deployment
    WEBAPP_URL = "https://oleg-project-sklad.github.io/webapp/" 
    
    rows = [
        [KeyboardButton("📝 Форма (Web App)", web_app=WebAppInfo(url=WEBAPP_URL))],
        ["📝 Создать (Текст)"],
        ["❓ Помощь"]
    ]
    
    is_admin = False
    if admin_ids:
        is_admin = user_id in admin_ids
        
    if is_admin:
        rows.insert(2, ["📊 Отчёты"])
        rows.append(["⚙️ Админка"])
        
    return build_keyboard(rows)
