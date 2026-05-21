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
        
        # 1. SMART GUARD: Duplicate tracking
        await db.execute('''CREATE TABLE IF NOT EXISTS processed_tickets (
            ticket_number TEXT,
            issue_number TEXT,
            date TEXT,
            user_id INTEGER,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (ticket_number)
        )''')
        
        # 2. GAMIFICATION: User Stats
        await db.execute('''CREATE TABLE IF NOT EXISTS user_stats (
            user_id INTEGER PRIMARY KEY,
            total_tickets INTEGER DEFAULT 0,
            total_value INTEGER DEFAULT 0,
            weekly_tickets INTEGER DEFAULT 0,
            weekly_points INTEGER DEFAULT 0,
            highest_single_value INTEGER DEFAULT 0,
            points INTEGER DEFAULT 0,
            rank_title TEXT DEFAULT 'Новичок',
            achievements TEXT DEFAULT '[]',
            last_updated TEXT DEFAULT CURRENT_TIMESTAMP
        )''')

        # 2.1 QUIZ: Engagement tracking
        await db.execute('''CREATE TABLE IF NOT EXISTS quiz_attempts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            region TEXT,
            correct INTEGER DEFAULT 0,
            wrong INTEGER DEFAULT 0,
            total INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )''')

        # 3. SETTINGS: Global Config
        await db.execute('''CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY, value TEXT
        )''')
        await db.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('current_theme', 'default')")
        await db.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('cache_version', '1')")
        
        # Performance optimization indexes
        await db.execute("CREATE INDEX IF NOT EXISTS idx_user_stats_points ON user_stats(points DESC)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_processed_tickets_created ON processed_tickets(created_at)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_quiz_attempts_created ON quiz_attempts(created_at)")
        
        # Migration: Ensure columns exist
        migrations = [
            "ALTER TABLE user_stats ADD COLUMN achievements TEXT DEFAULT '[]'",
            "ALTER TABLE user_stats ADD COLUMN weekly_tickets INTEGER DEFAULT 0",
            "ALTER TABLE user_stats ADD COLUMN weekly_points INTEGER DEFAULT 0",
            "ALTER TABLE users ADD COLUMN last_region TEXT",
            "ALTER TABLE users ADD COLUMN is_blocked INTEGER DEFAULT 0",
            "ALTER TABLE users ADD COLUMN blocked_at TEXT",
            "ALTER TABLE users ADD COLUMN blocked_reason TEXT"
        ]
        for m in migrations:
            try:
                await db.execute(m)
            except Exception:
                pass # Column already exists

        try:
            await db.execute("UPDATE users SET is_blocked = 0 WHERE is_blocked IS NULL")
        except Exception:
            pass
            
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

# --- SMART GUARD HELPER ---
async def check_ticket_duplicate(ticket_number: str) -> Optional[Dict[str, Any]]:
    """Checks if a ticket has already been processed."""
    if not _is_db_ready(): return None
    async with db_lock:
        try:
            async with db.execute('SELECT user_id, date, created_at FROM processed_tickets WHERE ticket_number = ?', (ticket_number,)) as cursor:
                row = await cursor.fetchone()
                if row:
                    return {'user_id': row[0], 'date': row[1], 'created_at': row[2]}
        except Exception as e:
            logger.error(f"DB Error checking duplicate: {e}")
    return None

async def register_processed_ticket(ticket_number: str, issue_number: str, date: str, user_id: int) -> None:
    """Registers a processed ticket to prevent duplicates."""
    if not _is_db_ready(): return
    async with db_lock:
        try:
            await db.execute(
                'INSERT OR REPLACE INTO processed_tickets (ticket_number, issue_number, date, user_id) VALUES (?, ?, ?, ?)',
                (ticket_number, issue_number, date, user_id)
            )
            await db.commit()
        except Exception as e:
            logger.error(f"DB Error registering ticket: {e}")

# --- GAMIFICATION HELPERS ---
async def update_user_stats(user_id: int, ticket_value: int) -> Dict[str, Any]:
    """Updates user stats and returns new stats including achievements and weekly tracking."""
    if not _is_db_ready(): return {}
    async with db_lock:
        try:
            # Get current stats
            async with db.execute('SELECT total_tickets, total_value, highest_single_value, points, rank_title, achievements, weekly_tickets, weekly_points FROM user_stats WHERE user_id = ?', (user_id,)) as cursor:
                row = await cursor.fetchone()
                
            if row:
                total_tickets, total_value, highest, points, rank, achievements_json, weekly_tickets, weekly_points = row
                achievements = json.loads(achievements_json)
            else:
                total_tickets, total_value, highest, points, rank, achievements, weekly_tickets, weekly_points = 0, 0, 0, 0, 'Новичок', [], 0, 0
            
            # Update values
            total_tickets += 1
            weekly_tickets += 1
            total_value += ticket_value
            if ticket_value > highest:
                highest = ticket_value
            
            # Points logic: 10 per ticket + 1 per 1000 rub
            points_to_add = 10 + (ticket_value // 1000)
            points += points_to_add
            weekly_points += points_to_add
            
            # Rank logic (Expanded 8-level system)
            new_rank = rank
            if points >= 10000: new_rank = '👑 Легенда'
            elif points >= 5000: new_rank = '💎 Эксперт'
            elif points >= 2500: new_rank = '🚀 Профи'
            elif points >= 1000: new_rank = '🏆 Мастер'
            elif points >= 400: new_rank = '🎖 Специалист'
            elif points >= 150: new_rank = '🥇 Стажер'
            elif points >= 50: new_rank = '🥈 Ученик'
            else: new_rank = '🥉 Новичок'
            
            rank_up = (new_rank != rank)
            
            # Achievements Logic
            new_achievements = []
            milestones = [
                (1, "🥉 Первооткрыватель"),
                (10, "🥈 Опытный мастер"),
                (50, "🥇 Гуру оценки"),
                (100, "👑 Легенда Склада")
            ]
            
            for count, title in milestones:
                if total_tickets >= count and title not in achievements:
                    achievements.append(title)
                    new_achievements.append(title)
            
            if total_value >= 1000000 and "💰 Миллионер" not in achievements:
                achievements.append("💰 Миллионер")
                new_achievements.append("💰 Миллионер")

            if highest >= 500000 and "💎 Золотой глаз" not in achievements:
                achievements.append("💎 Золотой глаз")
                new_achievements.append("💎 Золотой глаз")
            
            await db.execute(
                '''INSERT OR REPLACE INTO user_stats (user_id, total_tickets, total_value, highest_single_value, points, rank_title, achievements, weekly_tickets, weekly_points, last_updated)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)''',
                (user_id, total_tickets, total_value, highest, points, new_rank, json.dumps(achievements), weekly_tickets, weekly_points)
            )
            await db.commit()
            
            return {
                'rank_up': rank_up,
                'new_rank': new_rank,
                'points': points,
                'total_tickets': total_tickets,
                'new_achievements': new_achievements,
                'weekly_tickets': weekly_tickets,
                'weekly_points': weekly_points
            }
        except Exception as e:
            logger.error(f"DB Error updating stats: {e}")
            return {}

async def get_leaderboard(limit: int = 5) -> list:
    """Returns top users by points, excluding admins."""
    if not _is_db_ready(): return []
    
    from modern_bot.config import DEFAULT_ADMIN_IDS
    
    async with db_lock:
        try:
            # Build placeholders for admins
            placeholders = ','.join('?' for _ in DEFAULT_ADMIN_IDS)
            query = f'''
                SELECT u.first_name, s.points, s.total_tickets, s.rank_title 
                FROM user_stats s
                LEFT JOIN users u ON s.user_id = u.user_id
                WHERE s.user_id NOT IN ({placeholders})
                ORDER BY s.points DESC
                LIMIT ?
            '''
            params = list(DEFAULT_ADMIN_IDS) + [limit]
            
            async with db.execute(query, params) as cursor:
                return await cursor.fetchall()
        except Exception as e:
            logger.error(f"DB Error getting leaderboard: {e}")
            return []

async def update_user_info(user_id: int, username: str, first_name: str, last_name: str, last_region: Optional[str] = None) -> None:
    """Updates user profile info for leaderboard."""
    if not _is_db_ready(): return
    async with db_lock:
        try:
            await db.execute(
                '''INSERT INTO users (user_id, username, first_name, last_name, last_active, last_region)
                   VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP, ?)
                   ON CONFLICT(user_id) DO UPDATE SET
                   username=excluded.username,
                   first_name=excluded.first_name,
                   last_name=excluded.last_name,
                   last_active=CURRENT_TIMESTAMP,
                   last_region=COALESCE(excluded.last_region, users.last_region)''',
                (user_id, username, first_name, last_name, last_region)
            )
            await db.commit()
        except Exception as e:
            logger.error(f"DB Error updating user info: {e}")

async def is_user_blocked(user_id: int) -> bool:
    """Check if a user is blocked."""
    if not _is_db_ready(): return False
    async with db_lock:
        try:
            async with db.execute('SELECT is_blocked FROM users WHERE user_id = ?', (user_id,)) as cursor:
                row = await cursor.fetchone()
                if row and row[0] is not None:
                    return bool(row[0])
        except Exception as e:
            logger.error(f"DB Error checking user block: {e}")
    return False

async def set_user_blocked(user_id: int, blocked: bool, reason: Optional[str] = None) -> bool:
    """Block or unblock a user."""
    if not _is_db_ready(): return False
    async with db_lock:
        try:
            await db.execute(
                "INSERT OR IGNORE INTO users (user_id, last_active) VALUES (?, CURRENT_TIMESTAMP)",
                (user_id,)
            )
            if blocked:
                await db.execute(
                    "UPDATE users SET is_blocked = 1, blocked_at = CURRENT_TIMESTAMP, blocked_reason = ? WHERE user_id = ?",
                    (reason, user_id)
                )
            else:
                await db.execute(
                    "UPDATE users SET is_blocked = 0, blocked_at = NULL, blocked_reason = NULL WHERE user_id = ?",
                    (user_id,)
                )
            await db.commit()
            return True
        except Exception as e:
            logger.error(f"DB Error updating block status: {e}")
            return False

async def get_all_user_stats() -> list:
    """Returns all user stats joined with user names."""
    if not _is_db_ready(): return []
    async with db_lock:
        try:
            query = '''
                SELECT s.user_id, u.first_name, s.total_tickets, s.points, s.rank_title, s.weekly_tickets, s.weekly_points, s.achievements
                FROM user_stats s
                LEFT JOIN users u ON s.user_id = u.user_id
            '''
            async with db.execute(query) as cursor:
                return await cursor.fetchall()
        except Exception as e:
            logger.error(f"DB Error getting all stats: {e}")
            return []

async def reset_weekly_stats() -> None:
    """Resets weekly stats for all users."""
    if not _is_db_ready(): return
    async with db_lock:
        try:
            await db.execute('UPDATE user_stats SET weekly_tickets = 0, weekly_points = 0')
            await db.commit()
            logger.info("Weekly stats reset for all users.")
        except Exception as e:
            logger.error(f"DB Error resetting weekly stats: {e}")

async def prune_old_records(cutoff: "datetime") -> Dict[str, int]:
    """Remove records older than cutoff (non-admin users only)."""
    if not _is_db_ready():
        return {}

    from datetime import datetime
    from modern_bot.config import DEFAULT_ADMIN_IDS

    if not isinstance(cutoff, datetime):
        return {}

    cutoff_iso = cutoff.isoformat(timespec="seconds")
    admin_ids = sorted({int(x) for x in DEFAULT_ADMIN_IDS if str(x).isdigit()})
    placeholders = ",".join("?" for _ in admin_ids) if admin_ids else ""

    counts = {"processed_tickets": 0, "quiz_attempts": 0, "user_stats": 0, "users": 0, "user_data": 0}

    async with db_lock:
        try:
            async with db.execute(
                "SELECT COUNT(*) FROM processed_tickets WHERE datetime(created_at) < datetime(?)",
                (cutoff_iso,),
            ) as c:
                counts["processed_tickets"] = (await c.fetchone())[0]
            await db.execute(
                "DELETE FROM processed_tickets WHERE datetime(created_at) < datetime(?)",
                (cutoff_iso,),
            )

            async with db.execute(
                "SELECT COUNT(*) FROM quiz_attempts WHERE datetime(created_at) < datetime(?)",
                (cutoff_iso,),
            ) as c:
                counts["quiz_attempts"] = (await c.fetchone())[0]
            await db.execute(
                "DELETE FROM quiz_attempts WHERE datetime(created_at) < datetime(?)",
                (cutoff_iso,),
            )

            if admin_ids:
                stats_query = (
                    f"SELECT COUNT(*) FROM user_stats WHERE user_id NOT IN ({placeholders}) "
                    "AND datetime(last_updated) < datetime(?)"
                )
                stats_params = admin_ids + [cutoff_iso]
                async with db.execute(stats_query, stats_params) as c:
                    counts["user_stats"] = (await c.fetchone())[0]
                await db.execute(
                    f"DELETE FROM user_stats WHERE user_id NOT IN ({placeholders}) "
                    "AND datetime(last_updated) < datetime(?)",
                    stats_params,
                )

                users_query = (
                    f"SELECT COUNT(*) FROM users WHERE user_id NOT IN ({placeholders}) "
                    "AND datetime(COALESCE(last_active, created_at)) < datetime(?)"
                )
                users_params = admin_ids + [cutoff_iso]
                async with db.execute(users_query, users_params) as c:
                    counts["users"] = (await c.fetchone())[0]
                await db.execute(
                    f"DELETE FROM users WHERE user_id NOT IN ({placeholders}) "
                    "AND datetime(COALESCE(last_active, created_at)) < datetime(?)",
                    users_params,
                )
            else:
                async with db.execute(
                    "SELECT COUNT(*) FROM user_stats WHERE datetime(last_updated) < datetime(?)",
                    (cutoff_iso,),
                ) as c:
                    counts["user_stats"] = (await c.fetchone())[0]
                await db.execute(
                    "DELETE FROM user_stats WHERE datetime(last_updated) < datetime(?)",
                    (cutoff_iso,),
                )

                async with db.execute(
                    "SELECT COUNT(*) FROM users WHERE datetime(COALESCE(last_active, created_at)) < datetime(?)",
                    (cutoff_iso,),
                ) as c:
                    counts["users"] = (await c.fetchone())[0]
                await db.execute(
                    "DELETE FROM users WHERE datetime(COALESCE(last_active, created_at)) < datetime(?)",
                    (cutoff_iso,),
                )

            async with db.execute("SELECT COUNT(*) FROM user_data WHERE user_id NOT IN (SELECT user_id FROM users)") as c:
                counts["user_data"] = (await c.fetchone())[0]
            await db.execute("DELETE FROM user_data WHERE user_id NOT IN (SELECT user_id FROM users)")

            await db.commit()
        except Exception as e:
            logger.error(f"DB Error pruning old records: {e}")
            return counts

    return counts

async def get_setting(key: str, default: Any = None) -> Any:
    """Returns a setting value from the database."""
    if not _is_db_ready(): return default
    async with db_lock:
        try:
            async with db.execute('SELECT value FROM settings WHERE key = ?', (key,)) as cursor:
                row = await cursor.fetchone()
                return row[0] if row else default
        except Exception as e:
            logger.error(f"DB Error getting setting {key}: {e}")
            return default

async def set_setting(key: str, value: Any) -> None:
    """Updates a setting value in the database."""
    if not _is_db_ready(): return
    async with db_lock:
        try:
            await db.execute('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)', (key, str(value)))
            await db.commit()
        except Exception as e:
            logger.error(f"DB Error setting {key}: {e}")
