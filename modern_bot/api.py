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

        user_id = 0 # Anonymous / Web User
        user_name = "Web User"
        
        # 2. Download Photos
        TEMP_PHOTOS_DIR.mkdir(parents=True, exist_ok=True)
        items = data.get('items', [])
        
        db_data = {
            'department_number': data['department_number'],
            'issue_number': data['issue_number'],
            'ticket_number': data['ticket_number'],
            'date': data['date'],
            'region': data['region'],
            'photo_desc': []
        }

        async with httpx.AsyncClient() as client:
            for item in items:
                photo_url = item.get('photo_url')
                description = item.get('description')
                evaluation = item.get('evaluation')
                
                if photo_url:
                    try:
                        response = await client.get(photo_url)
                        if response.status_code == 200:
                            unique_name = generate_unique_filename()
                            file_path = TEMP_PHOTOS_DIR / unique_name
                            with open(file_path, 'wb') as f:
                                f.write(response.content)
                            db_data['photo_desc'].append({
                                'photo': str(file_path),
                                'description': description,
                                'evaluation': evaluation
                            })
                    except Exception as e:
                        logger.error(f"Error downloading photo: {e}")

        # 3. Generate Document
        path = await create_document(user_id, user_name, db_data_override=db_data)
        
        # 4. Send to Group (if not test)
        is_test = data.get('is_test', False)
        if not is_test:
            bot = request.app['bot']
            region = data.get('region')
            topic_id = REGION_TOPICS.get(region)
            
            caption = (
                f"📄 Заключение от п. {data.get('department_number')}, "
                f"билет: {data.get('ticket_number')}, "
                f"от {data.get('date')}\n"
                f"🌍 Регион: {region}\n"
                f"(Создано через сайт)"
            )
            
            try:
                await send_document_from_path(
                    bot, 
                    MAIN_GROUP_CHAT_ID, 
                    path, 
                    message_thread_id=topic_id,
                    caption=caption
                )
            except Exception as e:
                logger.error(f"Failed to send to group: {e}")

        # 5. Return File
        if path and path.exists():
            with open(path, 'rb') as f:
                content = f.read()
            
            # Cleanup
            try:
                path.unlink()
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

async def handle_root(request):
    """Serve the index.html for testing"""
    from pathlib import Path
    html_path = Path(__file__).parent / 'web_app' / 'index.html'
    if html_path.exists():
        with open(html_path, 'r', encoding='utf-8') as f:
            return web.Response(text=f.read(), content_type='text/html')
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
