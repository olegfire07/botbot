import aiosqlite
import json
import logging
import asyncio
from typing import Dict, Any, Optional
from config.settings import settings

logger = logging.getLogger(__name__)

class DatabaseManager:
    def __init__(self, db_path):
        self.db_path = db_path
        self.conn: Optional[aiosqlite.Connection] = None
        self.lock = asyncio.Lock()

    async def connect(self):
        if self.conn:
            return
        self.conn = await aiosqlite.connect(self.db_path)
        await self.conn.execute("PRAGMA journal_mode=WAL;")
        await self.conn.execute("PRAGMA synchronous=NORMAL;")
        await self.conn.execute('''CREATE TABLE IF NOT EXISTS user_data (
            user_id INTEGER PRIMARY KEY, department_number TEXT, issue_number TEXT,
            date TEXT, photo_desc TEXT, region TEXT, ticket_number TEXT
        )''')
        await self.conn.execute('''CREATE TABLE IF NOT EXISTS user_settings (
            user_id INTEGER PRIMARY KEY, last_department TEXT, last_region TEXT
        )''')
        await self.conn.commit()
        logger.info("Database connected and initialized.")

    async def close(self):
        if self.conn:
            await self.conn.close()
            self.conn = None
            logger.info("Database connection closed.")

    async def save_user_data(self, user_id: int, data: Dict[str, Any]):
        if not self.conn:
            logger.error("Database not connected.")
            return
        async with self.lock:
            try:
                await self.conn.execute(
                    '''INSERT OR REPLACE INTO user_data (user_id, department_number, issue_number, date, region, ticket_number, photo_desc)
                       VALUES (?, ?, ?, ?, ?, ?, ?)''',
                    (user_id,
                     data.get('department_number'), data.get('issue_number'), data.get('date'),
                     data.get('region'), data.get('ticket_number'), json.dumps(data.get('photo_desc', [])))
                )
                await self.conn.commit()
            except Exception as e:
                logger.error(f"DB Error saving user {user_id}: {e}")

    async def load_user_data(self, user_id: int) -> Dict[str, Any]:
        if not self.conn:
            return {}
        async with self.lock:
            try:
                async with self.conn.execute('SELECT department_number, issue_number, date, region, ticket_number, photo_desc FROM user_data WHERE user_id = ?', (user_id,)) as cursor:
                    row = await cursor.fetchone()
                    if row:
                        return {
                            'department_number': row[0], 'issue_number': row[1], 'date': row[2],
                            'region': row[3], 'ticket_number': row[4], 'photo_desc': json.loads(row[5] or '[]')
                        }
            except Exception as e:
                logger.error(f"DB Error loading user {user_id}: {e}")
        return {}

    async def delete_user_data(self, user_id: int):
        if not self.conn:
            return
        async with self.lock:
            try:
                await self.conn.execute('DELETE FROM user_data WHERE user_id = ?', (user_id,))
                await self.conn.commit()
            except Exception as e:
                logger.error(f"DB Error deleting user {user_id}: {e}")

    async def get_user_settings(self, user_id: int) -> Dict[str, Any]:
        if not self.conn:
            return {}
        async with self.lock:
            try:
                async with self.conn.execute('SELECT last_department, last_region FROM user_settings WHERE user_id = ?', (user_id,)) as cursor:
                    row = await cursor.fetchone()
                    if row:
                        return {'last_department': row[0], 'last_region': row[1]}
            except Exception as e:
                logger.error(f"DB Error loading settings {user_id}: {e}")
        return {}

    async def update_user_settings(self, user_id: int, department: Optional[str] = None, region: Optional[str] = None):
        if not self.conn:
            return
        
        current = await self.get_user_settings(user_id)
        new_dept = department if department is not None else current.get('last_department')
        new_region = region if region is not None else current.get('last_region')
        
        async with self.lock:
            try:
                await self.conn.execute(
                    'INSERT OR REPLACE INTO user_settings (user_id, last_department, last_region) VALUES (?, ?, ?)',
                    (user_id, new_dept, new_region)
                )
                await self.conn.commit()
            except Exception as e:
                logger.error(f"DB Error saving settings {user_id}: {e}")

db = DatabaseManager(settings.DATABASE_FILE)
