import threading
import asyncio
import time
import pytest
from unittest.mock import MagicMock
from modern_bot.database.db import init_db, close_db
from modern_bot.api import start_api_server, stop_api_server

server_thread = None
loop = None

def run_server():
    global loop
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    async def start():
        await init_db()
        mock_bot = MagicMock()
        await start_api_server(mock_bot, host="127.0.0.1", port=8080)
        
    loop.run_until_complete(start())
    loop.run_forever()

@pytest.fixture(scope="session", autouse=True)
def test_server():
    global server_thread, loop
    
    # Ensure API_ENABLED is true for testing
    import modern_bot.api
    import modern_bot.config
    modern_bot.api.API_ENABLED = True
    modern_bot.config.API_ENABLED = True
    
    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()
    
    # Give the server a moment to bind and start listening
    time.sleep(1.5)
    
    yield
    
    if loop:
        async def stop():
            await stop_api_server()
            await close_db()
            loop.stop()
        asyncio.run_coroutine_threadsafe(stop(), loop)
    if server_thread:
        server_thread.join(timeout=2.0)
