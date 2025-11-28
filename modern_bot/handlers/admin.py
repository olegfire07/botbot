import json
import logging
from telegram import Update, BotCommand, BotCommandScopeChat
from telegram.ext import CallbackContext
from modern_bot.config import ADMIN_FILE, DEFAULT_ADMIN_IDS
from modern_bot.handlers.common import safe_reply

logger = logging.getLogger(__name__)
admin_ids = set()

def load_admin_ids() -> None:
    global admin_ids
    ids = set()
    if ADMIN_FILE.exists():
        try:
            with ADMIN_FILE.open("r", encoding="utf-8") as f:
                data = json.load(f)
            ids = {int(item) for item in data if isinstance(item, int) or (isinstance(item, str) and item.isdigit())}
        except (OSError, json.JSONDecodeError) as err:
            logger.warning(f"Не удалось прочитать список админов: {err}")
    if not ids:
        ids = set(DEFAULT_ADMIN_IDS)
        admin_ids = ids
        save_admin_ids()
    else:
        admin_ids = ids

def save_admin_ids() -> None:
    ADMIN_FILE.parent.mkdir(parents=True, exist_ok=True)
    with ADMIN_FILE.open("w", encoding="utf-8") as f:
        json.dump(sorted(admin_ids), f, ensure_ascii=False, indent=2)

def is_admin(user_id: int) -> bool:
    return user_id in admin_ids

async def add_admin_handler(update: Update, context: CallbackContext) -> None:
    requester_id = update.message.from_user.id
    if not is_admin(requester_id):
        await safe_reply(update, "Доступ запрещен.")
        return

    if not context.args:
        await safe_reply(update, "Использование: /add_admin <ID_ПОЛЬЗОВАТЕЛЯ>")
        return

    try:
        new_admin_id = int(context.args[0])
    except ValueError:
        await safe_reply(update, "ID должен быть числом.")
        return

    if new_admin_id in admin_ids:
        await safe_reply(update, "Пользователь уже является администратором.")
        return

    admin_ids.add(new_admin_id)
    save_admin_ids()
    await safe_reply(update, f"Пользователь {new_admin_id} добавлен как администратор.")

async def broadcast_handler(update: Update, context: CallbackContext) -> None:
    if not is_admin(update.message.from_user.id):
        await safe_reply(update, "Доступ запрещен.")
        return
    
    message = " ".join(context.args)
    if not message:
        await safe_reply(update, "Использование: /broadcast <сообщение>")
        return
        
    await safe_reply(update, f"Функция рассылки готова к подключению БД. Сообщение: {message}")

async def help_admin_handler(update: Update, context: CallbackContext) -> None:
    if not is_admin(update.message.from_user.id):
        return

    text = (
        "🔧 Справка администратора:\n"
        "/admin - Панель управления (все функции)\n\n"
        "📊 <b>Отчеты и статистика:</b>\n"
        "/history - Последние 10 записей\n"
        "/stats - Общая статистика\n"
        "/download_month ММ.ГГГГ [Регион] - Скачать архив\n"
        "/stats_period ДД.ММ.ГГГГ ДД.ММ.ГГГГ [Регион]\n"
        "/reports - Мастер отчетов\n\n"
        "👥 <b>Управление пользователями:</b>\n"
        "/add_user ID - Добавить пользователя\n"
        "/remove_user ID - Удалить пользователя\n"
        "/add_admin ID - Добавить админа\n"
        "/remove_admin ID - Удалить админа\n"
        "/broadcast Сообщение - Рассылка всем\n\n"
        "🔍 <b>Сверка билетов:</b> используйте кнопку в /admin панели. "
        "Поддерживаются файлы .txt и .xlsx."
    )
    await safe_reply(update, text, parse_mode="HTML")
