import aiosqlite
import json
import logging
import asyncio
from typing import Dict, Any, Optional
from pathlib import Path
from modern_bot.config import DATABASE_FILE

logger = logging.getLogger(__name__)

db: Optional[aiosqlite.Connection] = None
db_lock = asyncio.Lock()

def get_db() -> Optional[aiosqlite.Connection]:
    """Returns the current database connection."""
    return db

def _is_db_ready() -> bool:
    if db is None:
        logger.error("Database not initialized. Call init_db() first.")
        return False
    return True

async def init_db() -> None:
    """Initializes the database and creates the table if it doesn't exist."""
    global db
    
    # Close existing connection if any
    if db is not None:
        try:
            await db.close()
        except Exception:
            pass
        db = None
    
    try:
        db = await aiosqlite.connect(DATABASE_FILE)
        await db.execute("PRAGMA journal_mode=WAL;")
        await db.execute("PRAGMA synchronous=NORMAL;")
        
        # User drafts table
        await db.execute('''CREATE TABLE IF NOT EXISTS user_data (
            user_id INTEGER PRIMARY KEY, department_number TEXT, issue_number TEXT,
            date TEXT, photo_desc TEXT, region TEXT, ticket_number TEXT
        )''')
        
        # Users tracking table
        await db.execute('''CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            last_name TEXT,
            last_active TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )''')
        
        await db.commit()
        logger.info(f"Database initialized at {DATABASE_FILE}")
    except Exception as e:
        logger.critical(f"Failed to initialize database: {e}")
        raise

async def close_db(app=None) -> None:
    """Closes the database connection."""
    global db
    if db:
        await db.close()
        db = None
        logger.info("Database connection closed.")

async def save_user_data(user_id: int, data: Dict[str, Any]) -> None:
    """Saves user data to the database."""
    if not _is_db_ready():
        return
    async with db_lock:
        try:
            await db.execute(
                '''INSERT OR REPLACE INTO user_data (user_id, department_number, issue_number, date, region, ticket_number, photo_desc)
                   VALUES (?, ?, ?, ?, ?, ?, ?)''',
                (user_id,
                 data.get('department_number'), data.get('issue_number'), data.get('date'),
                 data.get('region'), data.get('ticket_number'), json.dumps(data.get('photo_desc', [])))
            )
            await db.commit()
        except Exception as e:
            logger.error(f"DB Error saving user {user_id}: {e}")

async def load_user_data(user_id: int) -> Dict[str, Any]:
    """Loads user data from the database."""
    if not _is_db_ready():
        return {}
    async with db_lock:
        try:
            async with db.execute('SELECT department_number, issue_number, date, region, ticket_number, photo_desc FROM user_data WHERE user_id = ?', (user_id,)) as cursor:
                row = await cursor.fetchone()
                if row:
                    return {
                        'department_number': row[0], 'issue_number': row[1], 'date': row[2],
                        'region': row[3], 'ticket_number': row[4], 'photo_desc': json.loads(row[5] or '[]')
                    }
        except Exception as e:
            logger.error(f"DB Error loading user {user_id}: {e}")
    return {}

async def delete_user_data(user_id: int) -> None:
    """Deletes user data from the database."""
    if not _is_db_ready():
        return
    async with db_lock:
        try:
            await db.execute('DELETE FROM user_data WHERE user_id = ?', (user_id,))
            await db.commit()
        except Exception as e:
            logger.error(f"DB Error deleting user {user_id}: {e}")
