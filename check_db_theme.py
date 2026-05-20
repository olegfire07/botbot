import asyncio
from modern_bot.database.db import init_db, get_setting

async def check():
    await init_db()
    theme = await get_setting("current_theme")
    print(f"DATABASE_THEME: {theme}")

if __name__ == "__main__":
    asyncio.run(check())
