import logging
from telegram import Update
from telegram.ext import CallbackContext
from modern_bot.database.db import get_db, db_lock
from modern_bot.handlers.admin import is_admin
from modern_bot.handlers.common import safe_reply

logger = logging.getLogger(__name__)

async def get_all_users():
    """Get list of all registered users."""
    async with db_lock:
        db = get_db()
        if db is None:
            logger.error("Database not initialized")
            return []
        try:
            async with db.execute(
                "SELECT user_id, username, first_name, last_name, last_active, last_region, is_blocked, blocked_at, blocked_reason FROM users ORDER BY last_active DESC"
            ) as cursor:
                rows = await cursor.fetchall()
                return [
                    {
                        "user_id": row[0],
                        "username": row[1],
                        "first_name": row[2],
                        "last_name": row[3],
                        "last_active": row[4],
                        "last_region": row[5],
                        "is_blocked": row[6],
                        "blocked_at": row[7],
                        "blocked_reason": row[8]
                    }
                    for row in rows
                ]
        except Exception as e:
            logger.error(f"Error fetching users: {e}")
            return []

async def add_user(user_id: int, username: str = None, first_name: str = None, last_name: str = None):
    """Add or update user in the database."""
    async with db_lock:
        db = get_db()
        if db is None:
            logger.error("Database not initialized")
            return False
        try:
            await db.execute(
                """INSERT INTO users (user_id, username, first_name, last_name, last_active)
                   VALUES (?, ?, ?, ?, datetime('now'))
                   ON CONFLICT(user_id) DO UPDATE SET
                   username=excluded.username,
                   first_name=excluded.first_name,
                   last_name=excluded.last_name,
                   last_active=datetime('now')""",
                (user_id, username, first_name, last_name)
            )
            await db.commit()
            return True
        except Exception as e:
            logger.error(f"Error adding user {user_id}: {e}")
            return False

async def remove_user(user_id: int):
    """Remove user from database."""
    async with db_lock:
        db = get_db()
        if db is None:
            return False
        try:
            await db.execute("DELETE FROM users WHERE user_id = ?", (user_id,))
            await db.commit()
            return True
        except Exception as e:
            logger.error(f"Error removing user {user_id}: {e}")
            return False

async def get_user_info(user_id: int):
    """Get user information."""
    async with db_lock:
        db = get_db()
        if db is None:
            return None
        try:
            async with db.execute(
                "SELECT user_id, username, first_name, last_name, last_active, last_region, is_blocked, blocked_at, blocked_reason FROM users WHERE user_id = ?",
                (user_id,)
            ) as cursor:
                row = await cursor.fetchone()
                if row:
                    return {
                        "user_id": row[0],
                        "username": row[1],
                        "first_name": row[2],
                        "last_name": row[3],
                        "last_active": row[4],
                        "last_region": row[5],
                        "is_blocked": row[6],
                        "blocked_at": row[7],
                        "blocked_reason": row[8]
                    }
                return None
        except Exception as e:
            logger.error(f"Error fetching user {user_id}: {e}")
            return None

# Handlers
async def list_users_handler(update: Update, context: CallbackContext) -> str:
    """Return formatted list of users."""
    users = await get_all_users()
    
    if not users:
        return "📋 База пользователей пуста."
    
    text = f"👥 <b>Всего пользователей:</b> {len(users)}\n\n"
    
    for i, user in enumerate(users[:50], 1):  # Limit to 50
        name = user.get('first_name', '') or user.get('username', 'Без имени')
        last_name = user.get('last_name', '')
        full_name = f"{name} {last_name}".strip()
        username = f"@{user['username']}" if user.get('username') else ''
        region = user.get('last_region') or ''
        blocked = user.get('is_blocked')
        status = "⛔" if blocked else ""
        region_text = f" ({region})" if region else ""
        
        text += f"{i}. <code>{user['user_id']}</code> - {full_name} {username} {status}{region_text}\n"
    
    if len(users) > 50:
        text += f"\n... и ещё {len(users) - 50} пользователей"
    
    return text

async def add_user_by_id(user_id: int, added_by: int) -> str:
    """Add user by ID."""
    if not is_admin(added_by):
        return "❌ Доступ запрещен."
    
    # Check if user already exists
    existing = await get_user_info(user_id)
    if existing:
        return f"ℹ️ Пользователь {user_id} уже в базе."
    
    success = await add_user(user_id)
    if success:
        return f"✅ Пользователь {user_id} добавлен."
    else:
        return f"❌ Ошибка при добавлении пользователя."

async def remove_user_by_id(user_id: int, removed_by: int) -> str:
    """Remove user by ID."""
    if not is_admin(removed_by):
        return "❌ Доступ запрещен."
    
    # Check if user exists
    existing = await get_user_info(user_id)
    if not existing:
        return f"ℹ️ Пользователь {user_id} не найден в базе."
    
    success = await remove_user(user_id)
    if success:
        return f"✅ Пользователь {user_id} удалён."
    else:
        return f"❌ Ошибка при удалении пользователя."
