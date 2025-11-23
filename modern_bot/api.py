import logging
import json
import asyncio
from aiohttp import web
from modern_bot.services.docx_gen import create_document
from modern_bot.services.flow import finalize_conclusion, send_document_from_path
from modern_bot.config import TEMP_PHOTOS_DIR, MAIN_GROUP_CHAT_ID, REGION_TOPICS
from modern_bot.utils.files import generate_unique_filename
from modern_bot.database.db import save_user_data
import httpx
import os

logger = logging.getLogger(__name__)

async def handle_generate(request):
    """
    Handle POST /api/generate
    """
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
                    'Access-Control-Allow-Origin': '*'
                }
            )
        else:
            return web.json_response({'error': 'Failed to generate document'}, status=500)

    except Exception as e:
        logger.error(f"API Error: {e}", exc_info=True)
        return web.json_response({'error': str(e)}, status=500, headers={'Access-Control-Allow-Origin': '*'})

async def handle_options(request):
    return web.Response(headers={
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'POST, OPTIONS',
        'Access-Control-Allow-Headers': 'Content-Type'
    })

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
    from modern_bot.config import ARCHIVE_DIR
    
    try:
        now = datetime.now()
        subdir_name = now.strftime("%Y-%m")
        month_dir = ARCHIVE_DIR / subdir_name
        
        count = 0
        if month_dir.exists():
            # Count files, excluding hidden ones
            count = len([f for f in month_dir.iterdir() if f.is_file() and not f.name.startswith('.')])
            
        return web.json_response({'count': count, 'month': subdir_name}, headers={'Access-Control-Allow-Origin': '*'})
    except Exception as e:
        logger.error(f"Stats Error: {e}")
        return web.json_response({'error': str(e)}, status=500)

async def start_api_server(bot, port=8080):
    app = web.Application()
    app['bot'] = bot
    app.router.add_get('/', handle_root)
    app.router.add_get('/api/stats', handle_stats)
    app.router.add_post('/api/generate', handle_generate)
    app.router.add_options('/api/generate', handle_options)
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    logger.info(f"API Server started on port {port}")
