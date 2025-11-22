# Modern Bot

This is the refactored and improved version of the conclusion bot.

## Features
- **Modular Structure**: Clean code organized in `modern_bot/`.
- **Web App**: "Fool-proof" data entry via a Telegram Mini App.
- **Monetization**: `/broadcast` command to send messages to all users.
- **Improved Reports**: Better archive handling and stats.

## How to Run
1.  Ensure you are in the project root (`/Users/oleg/Project_SKLAD`).
2.  Run the bot:
    ```bash
    python3 run_modern_bot.py
    ```

## Web App Setup
To use the Web App:
1.  Host the file `modern_bot/web_app/index.html` on a public server (GitHub Pages, Glitch, Netlify).
2.  Update the URL in `modern_bot/handlers/start.py` (currently a placeholder).
3.  Create a new bot via BotFather and enable "Menu Button" -> "Configure Menu Button" -> send the URL.
    OR just use the keyboard button provided in `/start`.

## Admin Commands
- `/add_admin <ID>`
- `/broadcast <Message>`
- `/download_month <MM.YYYY>`
- `/stats`
