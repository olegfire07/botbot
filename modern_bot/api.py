import logging
import asyncio
import os
from aiohttp import web
from modern_bot.config import (
    API_ENABLED,
    API_PORT,
    API_BIND_HOST,
    API_AUTH_TOKEN,
    API_MAX_REQUEST_SIZE_MB,
    ARCHIVE_DIR,
)

logger = logging.getLogger(__name__)

# CORS allowed origins (load from environment for security)
ALLOWED_ORIGINS = os.getenv(
    "ALLOWED_ORIGINS", 
    "https://olegfire07.github.io"
).split(",")

def _get_cors_headers(request):
    """Get CORS headers for specific origin (security: no wildcard)"""
    origin = request.headers.get("Origin", "")
    if any(origin.startswith(allowed.strip()) for allowed in ALLOWED_ORIGINS):
        return {
            "Access-Control-Allow-Origin": origin,
            "Access-Control-Allow-Methods": "POST, GET, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type, X-API-KEY"
        }
    return {}

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
            except:
                pass
                
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

async def handle_options(request):
    return web.Response(headers=_get_cors_headers(request))

async def handle_root(request):
    """Serve the index.html with injected config"""
    from pathlib import Path
    import os
    
    html_path = Path(__file__).parent / 'web_app' / 'index.html'
    if html_path.exists():
        with open(html_path, 'r', encoding='utf-8') as f:
            content = f.read()
            
        # Inject Config
        bot_url = os.getenv("BOT_URL", "")
        imgbb_key = os.getenv("IMGBB_KEY", "")
        
        content = content.replace('window.APP_DEFAULT_BOT_URL || ""', f'"{bot_url}"')
        content = content.replace('window.APP_DEFAULT_IMGBB_KEY || ""', f'"{imgbb_key}"')
        
        return web.Response(text=content, content_type='text/html')
    return web.Response(text='Web app not found', status=404)

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
            # Count files, excluding hidden ones
            count = len([f for f in month_dir.iterdir() if f.is_file() and not f.name.startswith('.')])
            
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

async def start_api_server(bot, host: str = None, port: int = None):
    if not API_ENABLED:
        logger.info("API server disabled (API_ENABLED=false).")
        return

    bind_host = host or API_BIND_HOST
    bind_port = port or API_PORT
    max_size_bytes = max(API_MAX_REQUEST_SIZE_MB, 1) * 1024 * 1024

    app = web.Application(client_max_size=max_size_bytes)
    app['bot'] = bot
    app.router.add_get('/', handle_root)
    app.router.add_get('/api/stats', handle_stats)
    app.router.add_post('/api/generate', handle_generate)
    app.router.add_options('/api/generate', handle_options)
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, bind_host, bind_port)
    await site.start()
    logger.info(f"API Server started on http://{bind_host}:{bind_port} (max {max_size_bytes} bytes)")
