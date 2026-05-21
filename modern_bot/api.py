import logging
import asyncio
import os
import json
import time
import errno
from aiohttp import web
from modern_bot.config import (
    API_ENABLED,
    API_PORT,
    API_BIND_HOST,
    API_AUTH_TOKEN,
    API_MAX_REQUEST_SIZE_MB,
    ARCHIVE_DIR,
    DATABASE_FILE,
)

logger = logging.getLogger(__name__)

# Runtime references to avoid double-start and to support graceful cleanup.
_api_runner = None
_api_site = None
_api_host = None
_api_port = None
_api_lock = asyncio.Lock()

# CORS allowed origins (load from environment for security)
ALLOWED_ORIGINS = [
    x.strip() for x in os.getenv(
        "ALLOWED_ORIGINS", 
        "https://olegfire07.github.io,http://localhost:8000,http://localhost:3000,http://localhost:5000,http://localhost:5173,http://127.0.0.1:8000,http://127.0.0.1:3000,http://127.0.0.1:5000,http://127.0.0.1:5173"
    ).split(",")
]

def _get_cors_headers(request):
    """Get CORS headers with proper Origin validation against ALLOWED_ORIGINS."""
    origin = request.headers.get("Origin", "")
    
    # Smart validation for local development and file protocol
    if origin == "null" or origin == "file://":
        allowed_origin = origin
    elif origin.startswith("http://localhost:") or origin.startswith("http://127.0.0.1:"):
        allowed_origin = origin
    elif origin in ALLOWED_ORIGINS:
        allowed_origin = origin
    else:
        # Fall back to first allowed origin for safety
        allowed_origin = ALLOWED_ORIGINS[0] if ALLOWED_ORIGINS else ""
        
    return {
        "Access-Control-Allow-Origin": allowed_origin,
        "Access-Control-Allow-Methods": "POST, GET, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type, X-API-KEY",
        "Access-Control-Allow-Credentials": "true"
    }

def _unauthorized(request):
    return web.json_response(
        {"error": "Unauthorized"},
        status=401,
        headers=_get_cors_headers(request)
    )

def _is_authorized(request) -> bool:
    if not API_AUTH_TOKEN:
        return True
    return request.headers.get("X-API-KEY") == API_AUTH_TOKEN

async def _cleanup_temp_file(path, delay_seconds: int = 120) -> None:
    await asyncio.sleep(delay_seconds)
    try:
        if path.exists():
            path.unlink()
    except Exception as e:
        logger.warning("Failed to cleanup temp file %s: %s", path, e)

async def handle_generate(request):
    """
    Handle POST /api/generate
    """
    if not _is_authorized(request):
        return _unauthorized(request)

    try:
        # 1. Parse Data
        data = await request.json()
        
        # Basic Validation
        required_fields = ['department_number', 'issue_number', 'ticket_number', 'date', 'region', 'items']
        for field in required_fields:
            if field not in data:
                return web.json_response({'error': f'Missing field: {field}'}, status=400)
        
        # CRITICAL: Validate date is not in the future
        from datetime import datetime
        try:
            # Parse date in DD.MM.YYYY format
            date_str = data.get('date', '')
            date_obj = datetime.strptime(date_str, '%d.%m.%Y')
            today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            
            if date_obj > today:
                logger.warning(f"Rejected future date: {date_str}")
                return web.json_response({
                    'error': 'Нельзя выбрать будущую дату! Выберите сегодняшнюю или прошедшую дату.'
                }, status=400)
        except ValueError:
            return web.json_response({'error': 'Неверный формат даты. Используйте ДД.ММ.ГГГГ'}, status=400)

        # Delegate to ReportService
        from modern_bot.services.report import ReportService
        
        bot = request.app['bot']
        path = await ReportService.create_report(data, bot)

        # 5. Return File
        if path and path.exists():
            # Read file in thread to avoid blocking
            content = await asyncio.to_thread(path.read_bytes)
            
            # Cleanup
            try:
                await asyncio.to_thread(path.unlink)
            except Exception as e:
                logger.warning(f"Failed to delete temporary file: {e}")
                
            return web.Response(
                body=content,
                content_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                headers={
                    'Content-Disposition': f'attachment; filename="Conclusion_{data["ticket_number"]}.docx"',
                    **_get_cors_headers(request)
                }
            )
        else:
            return web.json_response({'error': 'Failed to generate document'}, status=500)

    except Exception as e:
        logger.error(f"API Error: {e}", exc_info=True)
        # ✅ Security: Don't expose error details
        return web.json_response(
            {'error': 'Internal server error'}, 
            status=500, 
            headers=_get_cors_headers(request)
        )

async def handle_upload_photo(request):
    """
    Handle POST /api/upload-photo
    Receives multipart/form-data with 'image' field.
    Stores locally or sends to Telegram and returns a reference.
    """
    if not _is_authorized(request):
        return _unauthorized(request)

    try:
        reader = await request.multipart()
        field = await reader.next()
        
        if field.name != 'image':
            return web.json_response({'error': 'Expected "image" field'}, status=400)
            
        filename = field.filename or "image.jpg"
        file_data = await field.read()
        
        if not file_data:
            return web.json_response({'error': 'Empty file'}, status=400)

        from pathlib import Path
        from modern_bot.config import PHOTO_STORAGE_CHAT_ID, TEMP_PHOTOS_DIR, MAX_PHOTO_SIZE_MB, PHOTO_STORE_MODE
        from modern_bot.utils.files import generate_unique_filename
        import io

        max_bytes = MAX_PHOTO_SIZE_MB * 1024 * 1024
        if len(file_data) > max_bytes:
            return web.json_response({'error': 'File too large'}, status=400)

        store_mode = (PHOTO_STORE_MODE or "local").strip().lower()

        if store_mode == "local":
            ext = Path(filename).suffix.lower()
            if ext not in {".jpg", ".jpeg", ".png", ".webp"}:
                ext = ".jpg"
            file_name = generate_unique_filename(extension=ext)
            TEMP_PHOTOS_DIR.mkdir(parents=True, exist_ok=True)
            file_path = TEMP_PHOTOS_DIR / file_name
            await asyncio.to_thread(file_path.write_bytes, file_data)

            logger.info(f"Photo stored locally: {file_path.name} ({len(file_data)} bytes)")

            return web.json_response({
                'data': {
                    'id': file_name,
                    'url': f"local:{file_name}",
                    'direct_url': f"local:{file_name}",
                    'display_url': f"local:{file_name}"
                },
                'success': True,
                'status': 200
            }, headers=_get_cors_headers(request))

        # Fallback: store in Telegram
        bot = request.app['bot']

        logger.info(f"Uploading photo {filename} ({len(file_data)} bytes) to Telegram chat {PHOTO_STORAGE_CHAT_ID}")

        photo_file = io.BytesIO(file_data)
        photo_file.name = filename

        msg = await bot.send_photo(
            chat_id=PHOTO_STORAGE_CHAT_ID,
            photo=photo_file,
            caption=f"Upload via WebApp: {filename}"
        )

        photo = msg.photo[-1]
        file_id = photo.file_id

        logger.info(f"Photo uploaded to Telegram. File ID: {file_id}")

        return web.json_response({
            'data': {
                'id': file_id,
                'url': f"tg:{file_id}",
                'direct_url': f"tg:{file_id}",
                'display_url': f"tg:{file_id}"
            },
            'success': True,
            'status': 200
        }, headers=_get_cors_headers(request))

    except Exception as e:
        logger.error(f"Upload Error: {e}", exc_info=True)
        return web.json_response(
            {'error': f'Upload failed: {str(e)}'}, 
            status=500,
            headers=_get_cors_headers(request)
        )

async def handle_quiz_submit(request):
    """Handle POST /api/quiz/submit to record quiz engagement."""
    try:
        data = await request.json()
    except Exception:
        return web.json_response(
            {'error': 'Invalid JSON'},
            status=400,
            headers=_get_cors_headers(request)
        )

    user_id = data.get("user_id")
    try:
        user_id = int(user_id) if user_id is not None else None
    except (TypeError, ValueError):
        return web.json_response(
            {'error': 'Invalid user_id'},
            status=400,
            headers=_get_cors_headers(request)
        )

    region = (data.get("region") or "").strip() or None

    try:
        correct = int(data.get("correct", 0))
        wrong = int(data.get("wrong", 0))
        total = int(data.get("total", correct + wrong))
    except (TypeError, ValueError):
        return web.json_response(
            {'error': 'Invalid quiz stats'},
            status=400,
            headers=_get_cors_headers(request)
        )

    correct = max(correct, 0)
    wrong = max(wrong, 0)
    total = max(total, 0)

    from modern_bot.database.db import get_db
    db = get_db()
    if not db:
        return web.json_response(
            {'error': 'Database not ready'},
            status=500,
            headers=_get_cors_headers(request)
        )
    await db.execute(
        "INSERT INTO quiz_attempts (user_id, region, correct, wrong, total) VALUES (?, ?, ?, ?, ?)",
        (user_id, region, correct, wrong, total)
    )
    await db.commit()
    return web.json_response({'status': 'ok'}, headers=_get_cors_headers(request))

async def handle_options(request):
    return web.Response(headers=_get_cors_headers(request))

async def handle_health(request):
    """Health check endpoint GET /health"""
    import time
    from pathlib import Path
    from modern_bot.config import DATABASE_FILE, BASE_DIR
    from modern_bot.version import __version__
    
    # Calculate uptime
    start_time = request.app.get('start_time', time.time())
    uptime_seconds = int(time.time() - start_time)
    uptime_str = f"{uptime_seconds // 3600}h {(uptime_seconds % 3600) // 60}m"
    
    # Check DB connection
    db_status = "connected" if DATABASE_FILE.exists() else "missing"
    
    health_data = {
        "status": "ok",
        "bot": "running",
        "database": db_status,
        "uptime": uptime_str,
        "version": __version__
    }
    
    return web.json_response(health_data, headers=_get_cors_headers(request))

async def handle_root(request):
    """Serve the index.html with injected config"""
    from pathlib import Path
    import os

    def _find_web_app():
        """Use unified modern_bot/web_app path"""
        return Path(__file__).resolve().parent / 'web_app' / 'index.html'

    html_path = _find_web_app()
    if not html_path:
        return web.Response(text='Web app not found', status=404)

    with open(html_path, 'r', encoding='utf-8') as f:
        content = f.read()
        
    # Inject Config
    bot_url = os.getenv("BOT_URL", "")
    from modern_bot.database.db import get_setting
    current_theme = await get_setting('current_theme', 'default')
    
    content = content.replace('window.APP_DEFAULT_BOT_URL || ""', f'"{bot_url}"')
    content = content.replace("const ACTIVE_THEME = 'default';", f"const ACTIVE_THEME = '{current_theme}';")
    
    return web.Response(
        text=content, 
        content_type='text/html',
        headers={
            'Cache-Control': 'no-cache, no-store, must-revalidate',
            'Pragma': 'no-cache',
            'Expires': '0'
        }
    )

async def handle_super_admin(request):
    """Serve the super_admin.html page"""
    if not _is_authorized(request):
        return _unauthorized(request)
    from pathlib import Path
    html_path = Path(__file__).resolve().parent / 'web_app' / 'super_admin.html'
    if not html_path.exists():
        return web.Response(text='Super Admin App not found', status=404)
    with open(html_path, 'r', encoding='utf-8') as f:
        content = f.read()
    return web.Response(text=content, content_type='text/html')

async def api_super_admin_stats(request):
    if not _is_authorized(request):
        return _unauthorized(request)
    from modern_bot.database.db import get_db
    db = get_db()
    async with db.execute("SELECT COUNT(*) FROM user_stats") as c:
        total_users = (await c.fetchone())[0]
    async with db.execute("SELECT COUNT(*) FROM processed_tickets") as c:
        total_tickets = (await c.fetchone())[0]
        
    from modern_bot.config import DEFAULT_ADMIN_IDS
    total_admins = len(DEFAULT_ADMIN_IDS)
    
    avg_tickets = round(total_tickets / total_users, 2) if total_users > 0 else 0
    
    return web.json_response({
        "total_users": total_users,
        "total_tickets": total_tickets,
        "total_admins": total_admins,
        "avg_tickets": avg_tickets
    })

async def api_super_admin_health(request):
    """Return system health details"""
    if not _is_authorized(request):
        return _unauthorized(request)
    from modern_bot.database.db import get_db
    import os
    
    app = request.app
    uptime = time.time() - app.get('start_time', time.time())
    
    db_status = "ok"
    try:
        db = get_db()
        await db.execute("SELECT 1")
    except Exception:
        db_status = "error"
        
    db_size = 0
    if os.path.exists(DATABASE_FILE):
        db_size = round(os.path.getsize(DATABASE_FILE) / (1024 * 1024), 2)
        
    return web.json_response({
        "status": "online",
        "uptime": int(uptime),
        "database": db_status,
        "db_size": db_size,
        "bot_initialized": app.get('bot') is not None
    })

async def api_super_admin_stream(request):
    """Server-Sent Events stream for live updates"""
    if not _is_authorized(request):
        return _unauthorized(request)
    from modern_bot.database.db import get_db
    from modern_bot.config import DEFAULT_ADMIN_IDS

    resp = web.StreamResponse(
        status=200,
        headers={
            "Content-Type": "text/event-stream",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            **_get_cors_headers(request)
        }
    )
    await resp.prepare(request)

    try:
        while True:
            db = get_db()
            total_users = 0
            total_tickets = 0
            if db:
                async with db.execute("SELECT COUNT(*) FROM user_stats") as c:
                    total_users = (await c.fetchone())[0]
                async with db.execute("SELECT COUNT(*) FROM processed_tickets") as c:
                    total_tickets = (await c.fetchone())[0]

            total_admins = len(DEFAULT_ADMIN_IDS)
            avg_tickets = round(total_tickets / total_users, 2) if total_users > 0 else 0

            db_status = "ok"
            if db:
                try:
                    await db.execute("SELECT 1")
                except Exception:
                    db_status = "error"
            else:
                db_status = "error"

            db_size = 0
            if os.path.exists(DATABASE_FILE):
                db_size = round(os.path.getsize(DATABASE_FILE) / (1024 * 1024), 2)

            uptime = int(time.time() - request.app.get('start_time', time.time()))

            stats_payload = {
                "total_users": total_users,
                "total_tickets": total_tickets,
                "total_admins": total_admins,
                "avg_tickets": avg_tickets
            }
            health_payload = {
                "status": "online",
                "uptime": uptime,
                "database": db_status,
                "db_size": db_size,
                "bot_initialized": request.app.get('bot') is not None
            }

            await resp.write(f"event: stats\ndata: {json.dumps(stats_payload)}\n\n".encode("utf-8"))
            await resp.write(f"event: health\ndata: {json.dumps(health_payload)}\n\n".encode("utf-8"))
            await resp.write(b": ping\n\n")
            await resp.drain()
            await asyncio.sleep(8)
    except (asyncio.CancelledError, ConnectionResetError, BrokenPipeError):
        pass

    return resp



async def api_super_admin_clear_cache(request):
    """Force increment cache version for all users"""
    if not _is_authorized(request):
        return _unauthorized(request)
    from modern_bot.database.db import get_setting, set_setting
    cv = await get_setting('cache_version', '1')
    new_cv = str(int(cv) + 1)
    await set_setting('cache_version', new_cv)
    return web.json_response(
        {"status": "ok", "new_cv": new_cv},
        headers=_get_cors_headers(request)
    )



async def api_super_admin_users(request):
    if not _is_authorized(request):
        return _unauthorized(request)
    from modern_bot.database.db import get_db
    db = get_db()
    # JOIN with users table to get first_name
    query = """
        SELECT s.user_id, u.first_name, u.last_name, u.username, u.last_active,
               u.last_region, u.is_blocked, u.blocked_at, u.blocked_reason,
               s.rank_title, s.points, s.total_tickets, s.total_value,
               s.highest_single_value, s.weekly_tickets, s.weekly_points, s.last_updated
        FROM user_stats s
        LEFT JOIN users u ON s.user_id = u.user_id
    """
    async with db.execute(query) as c:
        rows = await c.fetchall()
    users = [{
        "user_id": r[0],
        "first_name": r[1],
        "last_name": r[2],
        "username": r[3],
        "last_active": r[4],
        "last_region": r[5],
        "is_blocked": r[6] or 0,
        "blocked_at": r[7],
        "blocked_reason": r[8],
        "rank": r[9],
        "points": r[10],
        "total_tickets": r[11],
        "total_value": r[12],
        "highest_single_value": r[13],
        "weekly_tickets": r[14],
        "weekly_points": r[15],
        "last_updated": r[16]
    } for r in rows]
    return web.json_response(users)

async def api_super_admin_update_user(request):
    """Update user rank/points"""
    if not _is_authorized(request):
        return _unauthorized(request)
    from modern_bot.database.db import get_db

    data = await request.json()
    user_id = data.get("user_id")
    if not user_id:
        return web.json_response({"error": "Missing user_id"}, status=400)

    rank_title = data.get("rank_title")
    points = data.get("points")

    updates = []
    params = []
    if rank_title is not None:
        rank_title = str(rank_title).strip()
        if not rank_title:
            return web.json_response({"error": "Empty rank_title"}, status=400)
        updates.append("rank_title = ?")
        params.append(rank_title)
    if points is not None:
        try:
            points = int(points)
        except (TypeError, ValueError):
            return web.json_response({"error": "Invalid points"}, status=400)
        if points < 0:
            points = 0
        updates.append("points = ?")
        params.append(points)

    if not updates:
        return web.json_response({"error": "No fields to update"}, status=400)

    db = get_db()
    await db.execute("INSERT OR IGNORE INTO user_stats (user_id) VALUES (?)", (user_id,))
    updates.append("last_updated = CURRENT_TIMESTAMP")
    query = f"UPDATE user_stats SET {', '.join(updates)} WHERE user_id = ?"
    params.append(user_id)
    await db.execute(query, tuple(params))
    await db.commit()
    return web.json_response({"status": "ok"})

async def api_super_admin_users_list(request):
    """Return list of registered users"""
    if not _is_authorized(request):
        return _unauthorized(request)
    from modern_bot.database.db import get_db
    db = get_db()
    query = """
        SELECT user_id, username, first_name, last_name, last_active, last_region, is_blocked, blocked_at, blocked_reason
        FROM users
        ORDER BY last_active DESC
    """
    async with db.execute(query) as c:
        rows = await c.fetchall()
    users = [{
        "user_id": r[0],
        "username": r[1],
        "first_name": r[2],
        "last_name": r[3],
        "last_active": r[4],
        "last_region": r[5],
        "is_blocked": r[6] or 0,
        "blocked_at": r[7],
        "blocked_reason": r[8]
    } for r in rows]
    return web.json_response(users)

async def api_super_admin_user_block(request):
    """Block or unblock a user."""
    if not _is_authorized(request):
        return _unauthorized(request)
    from modern_bot.database.db import set_user_blocked
    from modern_bot.config import SUPER_ADMIN_ID

    data = await request.json()
    user_id = data.get("user_id")
    blocked_raw = data.get("blocked")
    reason = data.get("reason")

    if user_id is None or blocked_raw is None:
        return web.json_response({"error": "Missing user_id or blocked"}, status=400)
    try:
        user_id = int(user_id)
    except (TypeError, ValueError):
        return web.json_response({"error": "Invalid user_id"}, status=400)

    if user_id == SUPER_ADMIN_ID:
        return web.json_response({"error": "Cannot block super admin"}, status=400)

    if isinstance(blocked_raw, bool):
        blocked = blocked_raw
    elif isinstance(blocked_raw, (int, float)):
        blocked = bool(blocked_raw)
    elif isinstance(blocked_raw, str):
        blocked = blocked_raw.strip().lower() in {"1", "true", "yes", "blocked"}
    else:
        return web.json_response({"error": "Invalid blocked flag"}, status=400)

    ok = await set_user_blocked(user_id, blocked, reason)
    if not ok:
        return web.json_response({"error": "Failed to update user"}, status=500)
    return web.json_response(
        {"status": "ok", "user_id": user_id, "is_blocked": blocked},
        headers=_get_cors_headers(request)
    )

async def api_super_admin_regions(request):
    """Return list of regions for filtering/broadcast."""
    if not _is_authorized(request):
        return _unauthorized(request)
    from modern_bot.database.db import get_db
    from modern_bot.config import REGION_TOPICS
    db = get_db()
    regions = set(REGION_TOPICS.keys())
    if db:
        try:
            async with db.execute(
                "SELECT DISTINCT last_region FROM users WHERE last_region IS NOT NULL AND last_region != ''"
            ) as c:
                rows = await c.fetchall()
            for row in rows:
                if row and row[0]:
                    regions.add(row[0])
        except Exception:
            pass
    return web.json_response({"regions": sorted(regions)}, headers=_get_cors_headers(request))

async def api_super_admin_broadcast(request):
    """Send a broadcast message to all or a region, excluding blocked users."""
    if not _is_authorized(request):
        return _unauthorized(request)
    from modern_bot.database.db import get_db
    from telegram.error import RetryAfter, TimedOut, NetworkError, TelegramError

    data = await request.json()
    message = (data.get("message") or "").strip()
    region = (data.get("region") or "").strip() or None

    if not message:
        return web.json_response({"error": "Empty message"}, status=400)

    db = get_db()
    if not db:
        return web.json_response({"error": "Database not ready"}, status=500)

    query = "SELECT user_id FROM users WHERE (is_blocked IS NULL OR is_blocked = 0)"
    params = []
    if region:
        query += " AND last_region = ?"
        params.append(region)

    async with db.execute(query, params) as c:
        rows = await c.fetchall()

    user_ids = [row[0] for row in rows if row and row[0]]
    if not user_ids:
        return web.json_response(
            {"status": "ok", "sent": 0, "failed": 0, "target": region or "all"},
            headers=_get_cors_headers(request)
        )

    bot = request.app.get('bot')
    if not bot:
        return web.json_response({"error": "Bot not initialized"}, status=503)

    async def send_with_backoff(chat_id: int) -> bool:
        for attempt in range(3):
            try:
                await bot.send_message(chat_id=chat_id, text=message)
                return True
            except RetryAfter as e:
                await asyncio.sleep(getattr(e, "retry_after", 1) + 0.5)
            except (TimedOut, NetworkError):
                await asyncio.sleep(2 ** attempt)
            except TelegramError as e:
                logger.error(f"Broadcast failed for {chat_id}: {e}")
                return False
            except Exception as e:
                logger.error(f"Unexpected broadcast error for {chat_id}: {e}")
                return False
        return False

    sent = 0
    failed = 0
    for chat_id in user_ids:
        if await send_with_backoff(chat_id):
            sent += 1
        else:
            failed += 1
        await asyncio.sleep(0.15)

    return web.json_response(
        {"status": "ok", "sent": sent, "failed": failed, "target": region or "all"},
        headers=_get_cors_headers(request)
    )

async def api_super_admin_add_user(request):
    """Add a user to the registry"""
    if not _is_authorized(request):
        return _unauthorized(request)
    from modern_bot.database.db import get_db

    data = await request.json()
    user_id = data.get("user_id")
    if not user_id:
        return web.json_response({"error": "Missing user_id"}, status=400)
    try:
        user_id = int(user_id)
    except (TypeError, ValueError):
        return web.json_response({"error": "Invalid user_id"}, status=400)

    username = data.get("username")
    first_name = data.get("first_name")
    last_name = data.get("last_name")

    db = get_db()
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
    await db.execute("INSERT OR IGNORE INTO user_stats (user_id) VALUES (?)", (user_id,))
    await db.commit()
    return web.json_response({"status": "ok"})

async def api_super_admin_remove_user(request):
    """Remove a user from registry and stats"""
    if not _is_authorized(request):
        return _unauthorized(request)
    from modern_bot.database.db import get_db

    data = await request.json()
    user_id = data.get("user_id")
    if not user_id:
        return web.json_response({"error": "Missing user_id"}, status=400)
    try:
        user_id = int(user_id)
    except (TypeError, ValueError):
        return web.json_response({"error": "Invalid user_id"}, status=400)

    db = get_db()
    await db.execute("DELETE FROM users WHERE user_id = ?", (user_id,))
    await db.execute("DELETE FROM user_stats WHERE user_id = ?", (user_id,))
    await db.commit()
    return web.json_response({"status": "ok"})

async def api_super_admin_logs(request):
    """Return last 100-120 lines of logs using smart log-file detection"""
    if not _is_authorized(request):
        return _unauthorized(request)
    from pathlib import Path
    from datetime import datetime
    
    root_dir = Path(__file__).resolve().parent.parent
    
    # Try out.log first (stdout/stderr of nohup process)
    log_file = root_dir / 'out.log'
    
    # If out.log is missing or empty, try today's structured log file in logs/
    if not log_file.exists() or log_file.stat().st_size == 0:
        today_str = datetime.now().strftime('%Y-%m-%d')
        today_log = root_dir / 'logs' / f"bot_{today_str}.log"
        if today_log.exists():
            log_file = today_log
            
    # If today's log doesn't exist either, try to find the newest bot_*.log file
    if not log_file.exists() or log_file.stat().st_size == 0:
        logs_dir = root_dir / 'logs'
        if logs_dir.exists():
            bot_logs = list(logs_dir.glob('bot_*.log'))
            if bot_logs:
                bot_logs.sort(key=lambda p: p.stat().st_mtime, reverse=True)
                log_file = bot_logs[0]
                
    # Fallback to the legacy debug_launch_v6.log
    if not log_file.exists() or log_file.stat().st_size == 0:
        log_file = root_dir / 'debug_launch_v6.log'
        
    if not log_file.exists():
        return web.json_response({"logs": "Log file not found (tried out.log, logs/bot_*.log, debug_launch_v6.log)."})
        
    try:
        # Read the file with fallback encoding in case of issues
        try:
            with open(log_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
        except UnicodeDecodeError:
            with open(log_file, 'r', encoding='latin-1') as f:
                lines = f.readlines()
                
        last_lines = lines[-120:]  # increase lines count for better diagnostics
        header = f"--- Active log file: {log_file.name} --- (Last {len(last_lines)} lines)\n\n"
        return web.json_response({"logs": header + "".join(last_lines)})
    except Exception as e:
        return web.json_response({"logs": f"Error reading log file {log_file.name}: {e}"})

async def api_super_admin_tickets(request):
    """Return list of recent processed tickets"""
    if not _is_authorized(request):
        return _unauthorized(request)
    from modern_bot.database.db import get_db
    db = get_db()
    query = "SELECT ticket_number, issue_number, date, user_id, created_at FROM processed_tickets ORDER BY created_at DESC LIMIT 100"
    async with db.execute(query) as c:
        rows = await c.fetchall()
    tickets = [{"ticket": r[0], "issue": r[1], "date": r[2], "user_id": r[3], "created_at": r[4]} for r in rows]
    return web.json_response(tickets)

async def api_super_admin_delete_ticket(request):
    """Delete a specific ticket to allow re-submission"""
    if not _is_authorized(request):
        return _unauthorized(request)
    from modern_bot.database.db import get_db
    data = await request.json()
    ticket_num = data.get("ticket_number")
    if not ticket_num:
        return web.json_response({"error": "Missing ticket_number"}, status=400)
    db = get_db()
    await db.execute("DELETE FROM processed_tickets WHERE ticket_number = ?", (ticket_num,))
    await db.commit()
    logger.info(f"Super Admin deleted ticket {ticket_num}")
    return web.json_response({"status": "ok"})

async def api_super_admin_update_ticket(request):
    """Update issue/date for a ticket"""
    if not _is_authorized(request):
        return _unauthorized(request)
    from modern_bot.database.db import get_db
    import re

    data = await request.json()
    ticket_num = data.get("ticket_number")
    if not ticket_num:
        return web.json_response({"error": "Missing ticket_number"}, status=400)

    issue_number = data.get("issue_number")
    date_value = data.get("date")

    updates = []
    params = []
    if issue_number is not None:
        updates.append("issue_number = ?")
        params.append(str(issue_number))
    if date_value is not None:
        if date_value and not re.match(r"^\d{2}\.\d{2}\.\d{4}$", str(date_value)):
            return web.json_response({"error": "Invalid date format"}, status=400)
        updates.append("date = ?")
        params.append(str(date_value))

    if not updates:
        return web.json_response({"error": "No fields to update"}, status=400)

    db = get_db()
    async with db.execute("SELECT 1 FROM processed_tickets WHERE ticket_number = ?", (ticket_num,)) as c:
        if await c.fetchone() is None:
            return web.json_response({"error": "Ticket not found"}, status=404)

    query = f"UPDATE processed_tickets SET {', '.join(updates)} WHERE ticket_number = ?"
    params.append(ticket_num)
    await db.execute(query, tuple(params))
    await db.commit()
    return web.json_response({"status": "ok"})

async def api_super_admin_archives(request):
    """List generated archives"""
    if not _is_authorized(request):
        return _unauthorized(request)
    from pathlib import Path
    archives = []
    if ARCHIVE_DIR.exists():
        for item in ARCHIVE_DIR.rglob("*.zip"):
            if item.is_file():
                archives.append({
                    "name": item.name,
                    "path": str(item.relative_to(ARCHIVE_DIR)),
                    "size": item.stat().st_size,
                    "mtime": item.stat().st_mtime
                })
    return web.json_response(sorted(archives, key=lambda x: x['mtime'], reverse=True))

async def api_super_admin_download_archive(request):
    """Download a specific archive file"""
    if not _is_authorized(request):
        return _unauthorized(request)
    file_path = request.query.get("file")
    if not file_path:
        return web.Response(text="Missing file param", status=400)
    
    full_path = ARCHIVE_DIR / file_path
    if not full_path.exists() or not str(full_path.resolve()).startswith(str(ARCHIVE_DIR.resolve())):
        return web.Response(text="File not found or access denied", status=404)
        
    return web.FileResponse(full_path)

async def api_super_admin_export_archive(request):
    """Create and download archive ZIP for a period and optional region."""
    if not _is_authorized(request):
        return _unauthorized(request)
    from modern_bot.services.archive import get_archive_paths, create_archive_zip
    from modern_bot.utils.validators import parse_date_str

    start_text = (request.query.get("start") or "").strip()
    end_text = (request.query.get("end") or "").strip()
    region = (request.query.get("region") or "").strip()

    if not start_text or not end_text:
        return web.json_response({"error": "Missing start or end date"}, status=400, headers=_get_cors_headers(request))

    start_dt = parse_date_str(start_text)
    end_dt = parse_date_str(end_text)
    if not start_dt or not end_dt:
        return web.json_response({"error": "Invalid date format"}, status=400, headers=_get_cors_headers(request))

    if end_dt < start_dt:
        return web.json_response({"error": "End date must be after start date"}, status=400, headers=_get_cors_headers(request))

    if region.lower() in {"all", ""}:
        region = None

    paths = await get_archive_paths(start_dt, end_dt, region)
    if not paths:
        return web.json_response({"error": "No archives found"}, status=404, headers=_get_cors_headers(request))

    filename_prefix = f"archive_{start_text}-{end_text}" + (f"_{region}" if region else "")
    zip_path = await create_archive_zip(paths, filename_prefix)

    headers = _get_cors_headers(request)
    headers["Content-Disposition"] = f'attachment; filename="{zip_path.name}"'
    response = web.FileResponse(zip_path, headers=headers)
    asyncio.create_task(_cleanup_temp_file(zip_path))
    return response

async def api_super_admin_get_admins(request):
    """Get current admin IDs from admins.json"""
    if not _is_authorized(request):
        return _unauthorized(request)
    from modern_bot.handlers.admin import admin_ids, load_admin_ids
    from modern_bot.config import SUPER_ADMIN_ID
    from modern_bot.database.db import get_db

    if not admin_ids:
        load_admin_ids()

    admin_list = sorted(admin_ids)
    details = {}
    if admin_list:
        db = get_db()
        placeholders = ",".join("?" for _ in admin_list)
        query = f"SELECT user_id, username, first_name, last_name FROM users WHERE user_id IN ({placeholders})"
        async with db.execute(query, tuple(admin_list)) as c:
            rows = await c.fetchall()
        for r in rows:
            details[r[0]] = {"username": r[1], "first_name": r[2], "last_name": r[3]}

    admins = []
    for admin_id in admin_list:
        info = details.get(admin_id, {})
        admins.append({
            "user_id": admin_id,
            "username": info.get("username"),
            "first_name": info.get("first_name"),
            "last_name": info.get("last_name"),
            "is_super": admin_id == SUPER_ADMIN_ID
        })

    return web.json_response({"admins": admins, "super_admin_id": SUPER_ADMIN_ID})

async def api_super_admin_update_admins(request):
    """Update admin IDs in admins.json"""
    if not _is_authorized(request):
        return _unauthorized(request)
    from modern_bot.handlers.admin import admin_ids, load_admin_ids, save_admin_ids
    from modern_bot.config import SUPER_ADMIN_ID

    if not admin_ids:
        load_admin_ids()

    data = await request.json()
    new_admins = data.get("admins")
    action = data.get("action")
    user_id = data.get("user_id")

    if isinstance(new_admins, list):
        ids = set()
        for item in new_admins:
            try:
                ids.add(int(item))
            except (TypeError, ValueError):
                return web.json_response({"error": "Invalid admin id"}, status=400)
        ids.add(SUPER_ADMIN_ID)
        admin_ids.clear()
        admin_ids.update(ids)
        save_admin_ids()
        return await api_super_admin_get_admins(request)

    if action in {"add", "remove"} and user_id is not None:
        try:
            user_id = int(user_id)
        except (TypeError, ValueError):
            return web.json_response({"error": "Invalid user_id"}, status=400)

        if action == "remove" and user_id == SUPER_ADMIN_ID:
            return web.json_response({"error": "Cannot remove супер-админа"}, status=400)

        if action == "add":
            admin_ids.add(user_id)
        else:
            admin_ids.discard(user_id)
            admin_ids.add(SUPER_ADMIN_ID)

        save_admin_ids()
        return await api_super_admin_get_admins(request)

    return web.json_response({"error": "Invalid payload"}, status=400)

async def api_super_admin_charts_activity(request):
    """Return daily ticket activity for the last 14 days"""
    if not _is_authorized(request):
        return _unauthorized(request)
    from modern_bot.database.db import get_db
    from datetime import datetime, timedelta
    db = get_db()
    
    end_date = datetime.now()
    start_date = end_date - timedelta(days=14)
    
    query = """
        SELECT strftime('%Y-%m-%d', created_at) as day, COUNT(*) as count 
        FROM processed_tickets 
        WHERE created_at >= ?
        GROUP BY day 
        ORDER BY day ASC
    """
    async with db.execute(query, (start_date.isoformat(),)) as c:
        rows = await c.fetchall()
        
    activity = {row[0]: row[1] for row in rows}
    
    # Fill gaps with zeros
    data = []
    current = start_date
    while current <= end_date:
        day_str = current.strftime('%Y-%m-%d')
        data.append({"day": day_str, "count": activity.get(day_str, 0)})
        current += timedelta(days=1)
        
    return web.json_response(data)

async def api_super_admin_charts_growth(request):
    """Return cumulative user growth for the last 14 days"""
    if not _is_authorized(request):
        return _unauthorized(request)
    from modern_bot.database.db import get_db
    from datetime import datetime, timedelta
    db = get_db()
    
    end_date = datetime.now()
    start_date = end_date - timedelta(days=14)
    
    # Get total users before start_date
    async with db.execute("SELECT COUNT(*) FROM users WHERE created_at < ?", (start_date.isoformat(),)) as c:
        base_count = (await c.fetchone())[0]
        
    # Get daily new users
    query = """
        SELECT strftime('%Y-%m-%d', created_at) as day, COUNT(*) as count 
        FROM users 
        WHERE created_at >= ?
        GROUP BY day 
        ORDER BY day ASC
    """
    async with db.execute(query, (start_date.isoformat(),)) as c:
        rows = await c.fetchall()
        
    daily_new = {row[0]: row[1] for row in rows}
    
    data = []
    current = start_date
    cumulative = base_count
    while current <= end_date:
        day_str = current.strftime('%Y-%m-%d')
        cumulative += daily_new.get(day_str, 0)
        data.append({"day": day_str, "total": cumulative})
        current += timedelta(days=1)
        
    return web.json_response(data)

async def api_super_admin_monitoring(request):
    """Return monitoring stats for conclusions over a selected period."""
    if not _is_authorized(request):
        return _unauthorized(request)
    from datetime import datetime, timedelta
    from collections import Counter
    from modern_bot.services.excel import read_excel_data
    from modern_bot.utils.validators import parse_date_str
    from modern_bot.services.retention import get_effective_cutoff

    try:
        days = int(request.query.get("days", 30))
    except (TypeError, ValueError):
        days = 30
    days = max(1, min(days, 180))

    rows = await read_excel_data()
    cutoff = await get_effective_cutoff()

    today = datetime.now().date()
    period_start = today - timedelta(days=days - 1)
    prev_start = period_start - timedelta(days=days)
    prev_end = period_start - timedelta(days=1)

    daily_counts = {period_start + timedelta(days=i): 0 for i in range(days)}
    region_counts = Counter()
    total = 0
    prev_total = 0

    for row in rows:
        if len(row) <= 3 or not row[3]:
            continue
        dt = row[3] if isinstance(row[3], datetime) else parse_date_str(str(row[3]))
        if not dt:
            continue
        if dt < cutoff:
            continue
        day = dt.date()
        if period_start <= day <= today:
            total += 1
            daily_counts[day] = daily_counts.get(day, 0) + 1
            if len(row) > 4 and row[4]:
                region_counts[str(row[4])] += 1
        elif prev_start <= day <= prev_end:
            prev_total += 1

    daily = [{"day": d.isoformat(), "count": daily_counts[d]} for d in sorted(daily_counts.keys())]
    peak_entry = max(daily, key=lambda item: item["count"]) if daily else None
    peak_day = None
    if peak_entry and total > 0:
        peak_day = {"day": peak_entry["day"], "count": peak_entry["count"]}

    avg = round(total / days, 2) if days else 0
    growth_pct = None
    if prev_total > 0:
        growth_pct = round(((total - prev_total) / prev_total) * 100, 1)
    elif total > 0:
        growth_pct = 100.0

    regions = [{"region": region, "count": count} for region, count in region_counts.most_common()]

    return web.json_response({
        "days": days,
        "period": {"start": period_start.isoformat(), "end": today.isoformat()},
        "total": total,
        "prev_total": prev_total,
        "avg_per_day": avg,
        "growth_pct": growth_pct,
        "peak_day": peak_day,
        "daily": daily,
        "regions": regions
    })

async def api_super_admin_quiz_stats(request):
    """Return quiz engagement stats by region."""
    if not _is_authorized(request):
        return _unauthorized(request)
    from datetime import datetime, timedelta
    from modern_bot.database.db import get_db
    from modern_bot.services.retention import get_effective_cutoff

    try:
        days = int(request.query.get("days", 30))
    except (TypeError, ValueError):
        days = 30
    days = max(1, min(days, 180))

    cutoff = await get_effective_cutoff()
    start_dt = datetime.now() - timedelta(days=days - 1)
    if cutoff > start_dt:
        start_dt = cutoff

    start_iso = start_dt.isoformat(timespec="seconds")
    db = get_db()
    if not db:
        return web.json_response(
            {'error': 'Database not ready'},
            status=500,
            headers=_get_cors_headers(request)
        )

    async with db.execute(
        "SELECT COUNT(*), COUNT(DISTINCT user_id), SUM(correct), SUM(wrong), SUM(total) "
        "FROM quiz_attempts WHERE datetime(created_at) >= datetime(?)",
        (start_iso,),
    ) as c:
        row = await c.fetchone()

    total_attempts = row[0] or 0
    unique_users = row[1] or 0
    sum_correct = row[2] or 0
    sum_wrong = row[3] or 0
    sum_total = row[4] or 0

    avg_score_pct = round((sum_correct / sum_total) * 100, 1) if sum_total > 0 else 0
    avg_correct = round(sum_correct / total_attempts, 2) if total_attempts else 0
    avg_total = round(sum_total / total_attempts, 2) if total_attempts else 0

    async with db.execute(
        "SELECT COALESCE(NULLIF(TRIM(region), ''), 'Не указан') AS region, "
        "COUNT(*) AS attempts, COUNT(DISTINCT user_id) AS users "
        "FROM quiz_attempts WHERE datetime(created_at) >= datetime(?) "
        "GROUP BY region ORDER BY users DESC, attempts DESC",
        (start_iso,),
    ) as c:
        rows = await c.fetchall()

    regions = [
        {"region": r[0], "attempts": r[1] or 0, "users": r[2] or 0}
        for r in rows
    ]

    return web.json_response({
        "days": days,
        "period": {"start": start_dt.date().isoformat(), "end": datetime.now().date().isoformat()},
        "total_attempts": total_attempts,
        "unique_users": unique_users,
        "avg_score_pct": avg_score_pct,
        "avg_correct": avg_correct,
        "avg_total": avg_total,
        "regions": regions
    })

async def api_super_admin_system_restart(request):
    """Trigger a bot restart"""
    if not _is_authorized(request):
        return _unauthorized(request)
    logger.info("SYSTEM RESTART triggered via Super Admin Dashboard")
    # Schedule restart in 1 second to allow response to finish
    import sys
    import os
    import subprocess
    
    def restart():
        import time
        time.sleep(1)
        # Re-run same command
        # This is a bit OS dependent, but assuming we run as module
        os.execv(sys.executable, [sys.executable, '-m', 'modern_bot.main'])
        
    asyncio.create_task(asyncio.to_thread(restart))
    return web.json_response({"status": "restarting"})

async def api_super_admin_delete_user(request):
    if not _is_authorized(request):
        return _unauthorized(request)
    from modern_bot.database.db import get_db
    data = await request.json()
    user_id = data.get("user_id")
    if not user_id:
        return web.json_response({"error": "Missing user_id"}, status=400)
    db = get_db()
    await db.execute("DELETE FROM user_stats WHERE user_id = ?", (user_id,))
    await db.commit()
    logger.info(f"Super Admin deleted user {user_id}")
    return web.json_response({"status": "ok"})

async def api_super_admin_config(request):
    if not _is_authorized(request):
        return _unauthorized(request)
    from pathlib import Path
    env_path = Path(__file__).resolve().parent.parent / '.env'
    
    if request.method == "POST":
        data = await request.json()
        new_token = data.get("BOT_TOKEN")
        if new_token:
            # Aggressive .env update
            with open(env_path, 'r') as f:
                lines = f.readlines()
            new_lines = []
            found = False
            for line in lines:
                if line.startswith("BOT_TOKEN="):
                    new_lines.append(f"BOT_TOKEN={new_token}\n")
                    found = True
                else:
                    new_lines.append(line)
            if not found:
                new_lines.append(f"BOT_TOKEN={new_token}\n")
            
            with open(env_path, 'w') as f:
                f.writelines(new_lines)
            
            logger.info("Super Admin updated BOT_TOKEN. Bot will likely need a manual restart or we can trigger it.")
            # We don't trigger restart here to avoid killing the API while processing.
            return web.json_response({"status": "ok"})
            
    return web.json_response({"BOT_TOKEN": "********"})

async def handle_stats(request):
    """Return stats for the current month"""
    from datetime import datetime
    
    if not _is_authorized(request):
        return _unauthorized(request)

    try:
        now = datetime.now()
        subdir_name = now.strftime("%Y-%m")
        month_dir = ARCHIVE_DIR / subdir_name
        
        count = 0
        if month_dir.exists():
            # ✅ Count only ORIGINAL conclusions (not test)
            original_dir = month_dir / "original"
            if original_dir.exists():
                count = len([f for f in original_dir.iterdir() 
                           if f.is_file() and not f.name.startswith('.')])
            
        return web.json_response(
            {'count': count, 'month': subdir_name}, 
            headers=_get_cors_headers(request)
        )
    except Exception as e:
        logger.error(f"Stats Error: {e}")
        # ✅ Security: Don't expose error details
        return web.json_response(
            {'error': 'Internal server error'}, 
            status=500,
            headers=_get_cors_headers(request)
        )

async def handle_check_ticket(request):
    """
    Handle GET /api/check-ticket
    Checks if a ticket has already been processed and returns user details.
    """
    ticket_number = request.query.get('ticket', '').strip()
    if not ticket_number:
        return web.json_response(
            {'error': 'Missing ticket parameter'},
            status=400,
            headers=_get_cors_headers(request)
        )

    try:
        from modern_bot.database.db import get_db
        db = get_db()
        if not db:
            return web.json_response(
                {'error': 'Database not ready'},
                status=500,
                headers=_get_cors_headers(request)
            )

        query = """
            SELECT pt.user_id, pt.date, pt.created_at, u.first_name, u.last_name, u.username
            FROM processed_tickets pt
            LEFT JOIN users u ON pt.user_id = u.user_id
            WHERE pt.ticket_number = ?
        """
        async with db.execute(query, (ticket_number,)) as cursor:
            row = await cursor.fetchone()

        if row:
            user_id, date_str, created_at, first_name, last_name, username = row
            user_parts = []
            if first_name:
                user_parts.append(first_name)
            if last_name:
                user_parts.append(last_name)
            user_display = " ".join(user_parts) if user_parts else (username or f"ID {user_id}")

            return web.json_response(
                {
                    'duplicate': True,
                    'user': user_display,
                    'date': date_str or created_at
                },
                headers=_get_cors_headers(request)
            )
        else:
            return web.json_response(
                {'duplicate': False},
                headers=_get_cors_headers(request)
            )
    except Exception as e:
        logger.error(f"Check ticket error: {e}", exc_info=True)
        return web.json_response(
            {'error': 'Internal server error'},
            status=500,
            headers=_get_cors_headers(request)
        )

async def start_api_server(bot, host: str = None, port: int = None):
    if not API_ENABLED:
        logger.info("API server disabled (API_ENABLED=false).")
        return

    bind_host = host or API_BIND_HOST
    bind_port = port or API_PORT
    max_size_bytes = max(API_MAX_REQUEST_SIZE_MB, 1) * 1024 * 1024

    global _api_runner, _api_site, _api_host, _api_port
    async with _api_lock:
        if _api_runner is not None:
            # Keep bot reference fresh across restarts, but do not bind again.
            try:
                _api_runner.app['bot'] = bot
            except Exception:
                pass
            logger.info(f"API Server already running on http://{_api_host}:{_api_port}")
            return

        app = web.Application(client_max_size=max_size_bytes)
        app['bot'] = bot
        app['start_time'] = __import__('time').time()  # Track start time for uptime
        app.router.add_get('/', handle_root)
        app.router.add_get('/api/health', handle_health)
        app.router.add_get('/api/stats', handle_stats)
        
        # Super Admin Dashboard
        app.router.add_get('/super-admin', handle_super_admin)
        app.router.add_get('/api/super-admin/stats', api_super_admin_stats)
        app.router.add_get('/api/super-admin/health', api_super_admin_health)
        app.router.add_get('/api/super-admin/stream', api_super_admin_stream)
        app.router.add_get('/api/super-admin/users', api_super_admin_users)
        app.router.add_get('/api/super-admin/users/list', api_super_admin_users_list)
        app.router.add_post('/api/super-admin/user/update', api_super_admin_update_user)
        app.router.add_post('/api/super-admin/user/block', api_super_admin_user_block)
        app.router.add_get('/api/super-admin/regions', api_super_admin_regions)
        app.router.add_post('/api/super-admin/broadcast', api_super_admin_broadcast)
        app.router.add_post('/api/super-admin/user/add', api_super_admin_add_user)
        app.router.add_post('/api/super-admin/user/remove', api_super_admin_remove_user)
        app.router.add_get('/api/super-admin/logs', api_super_admin_logs)
        app.router.add_get('/api/super-admin/charts/activity', api_super_admin_charts_activity)
        app.router.add_get('/api/super-admin/charts/growth', api_super_admin_charts_growth)
        app.router.add_get('/api/super-admin/monitoring', api_super_admin_monitoring)
        app.router.add_get('/api/super-admin/quiz-stats', api_super_admin_quiz_stats)
        app.router.add_get('/api/super-admin/tickets', api_super_admin_tickets)
        app.router.add_post('/api/super-admin/ticket/delete', api_super_admin_delete_ticket)
        app.router.add_post('/api/super-admin/ticket/update', api_super_admin_update_ticket)
        app.router.add_get('/api/super-admin/archives', api_super_admin_archives)
        app.router.add_get('/api/super-admin/archives/download', api_super_admin_download_archive)
        app.router.add_get('/api/super-admin/archives/export', api_super_admin_export_archive)
        app.router.add_get('/api/super-admin/admins', api_super_admin_get_admins)
        app.router.add_post('/api/super-admin/admins', api_super_admin_update_admins)
        app.router.add_post('/api/super-admin/system/restart', api_super_admin_system_restart)
        app.router.add_post('/api/super-admin/user/delete', api_super_admin_delete_user)
        app.router.add_get('/api/super-admin/config', api_super_admin_config)
        app.router.add_post('/api/super-admin/config', api_super_admin_config)
        app.router.add_post('/api/super-admin/system/clear-cache', api_super_admin_clear_cache)
        app.router.add_options('/api/super-admin/system/clear-cache', handle_options)
        app.router.add_options('/api/super-admin/user/block', handle_options)
        app.router.add_options('/api/super-admin/broadcast', handle_options)
        app.router.add_post('/api/generate', handle_generate)
        app.router.add_options('/api/generate', handle_options)
        app.router.add_post('/api/upload-photo', handle_upload_photo)
        app.router.add_options('/api/upload-photo', handle_options)
        app.router.add_post('/api/quiz/submit', handle_quiz_submit)
        app.router.add_options('/api/quiz/submit', handle_options)
        app.router.add_get('/api/check-ticket', handle_check_ticket)
        app.router.add_options('/api/check-ticket', handle_options)
        # Static files from web_app directory (CSS, JS, images, etc.)
        from pathlib import Path
        web_app_dir = Path(__file__).resolve().parent / 'web_app'
        if web_app_dir.exists():
            app.router.add_static('/', web_app_dir, show_index=False)
            logger.info(f"Static files served from {web_app_dir}")

        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, bind_host, bind_port)
        try:
            await site.start()
        except OSError as e:
            await runner.cleanup()
            if e.errno in (errno.EADDRINUSE, 48, 98):
                logger.warning(
                    "API port is already in use (%s:%s). "
                    "Skipping API startup for this bot process.",
                    bind_host,
                    bind_port,
                )
                return
            raise

        _api_runner = runner
        _api_site = site
        _api_host = bind_host
        _api_port = bind_port
        logger.info(f"API Server started on http://{bind_host}:{bind_port} (max {max_size_bytes} bytes)")


async def stop_api_server():
    global _api_runner, _api_site, _api_host, _api_port
    async with _api_lock:
        if _api_runner is None:
            return
        host = _api_host
        port = _api_port
        try:
            await _api_runner.cleanup()
            logger.info(f"API Server stopped on http://{host}:{port}")
        except Exception as e:
            logger.warning(f"Failed to stop API server cleanly: {e}")
        finally:
            _api_runner = None
            _api_site = None
            _api_host = None
            _api_port = None
