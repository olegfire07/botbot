import logging
import json
from telegram import Update
from telegram.ext import ContextTypes, CallbackContext
from modern_bot.database.db import get_leaderboard, get_all_user_stats, reset_weekly_stats, get_db
from modern_bot.handlers.common import safe_reply

logger = logging.getLogger(__name__)

async def weekly_leaderboard_job(context: CallbackContext):
    """Job to send personal weekly summaries and a global top-3 to all participants."""
    try:
        logger.info("Running weekly leaderboard job...")
        
        # 1. Get Top-3 leaders for global context
        leaders = await get_leaderboard(limit=3)
        leaders_text = ""
        if leaders:
            medals = ["🥇", "🥈", "🥉"]
            leaders_text = "\n\n🏆 <b>Лидеры недели:</b>\n"
            for idx, (name, pts, tkts, rnk) in enumerate(leaders):
                medal = medals[idx]
                display_name = name if name else "Сотрудник"
                leaders_text += f"{medal} {display_name} ({tkts} закл. | {pts} баллов)\n"

        # 2. Get all users to send private summaries
        all_stats = await get_all_user_stats()
        
        sent_count = 0
        for user_id, first_name, total_tkts, total_pts, rank, weekly_tkts, weekly_pts, ach_json in all_stats:
            # Skip users with no activity this week
            if weekly_tkts == 0:
                continue
            
            try:
                display_name = first_name if first_name else "Коллега"
                
                # Format personal achievements
                achievements = json.loads(ach_json or '[]')
                ach_text = ", ".join(achievements[-3:]) if achievements else "пока нет"

                personal_msg = (
                    f"📈 <b>ИТОГИ НЕДЕЛИ</b>\n\n"
                    f"Привет, {display_name}! Вот твои успехи за прошедшую неделю:\n"
                    f"💼 Сделано заключений: <b>{weekly_tkts}</b>\n"
                    f"⭐ Получено баллов: <b>{weekly_pts}</b>\n\n"
                    f"🎖 Ваш текущий ранг: <b>{rank}</b>\n"
                    f"🏅 Награды: {ach_text}\n"
                    f"{leaders_text}"
                    f"\n<i>Продолжайте в том же духе! 💪</i>"
                )
                
                await context.bot.send_message(
                    chat_id=user_id,
                    text=personal_msg,
                    parse_mode="HTML"
                )
                sent_count += 1
            except Exception as user_err:
                logger.warning(f"Failed to send weekly stats to {user_id}: {user_err}")

        # 3. Reset weekly stats for next cycle
        await reset_weekly_stats()
        
        logger.info(f"Weekly job completed. Sent {sent_count} private summaries.")
        
    except Exception as e:
        logger.error(f"Failed to run weekly job: {e}")

async def my_stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Command /stats to show personal stats."""
    try:
        user = update.effective_user
        user_id = user.id
        
        db = get_db()
        if not db:
            await safe_reply(update, "⛔ База данных недоступна.")
            return

        async with db.execute('SELECT total_tickets, total_value, points, rank_title, achievements FROM user_stats WHERE user_id = ?', (user_id,)) as cursor:
            row = await cursor.fetchone()
            
        if not row:
            await safe_reply(update, "📊 У вас пока нет статистики. Обработайте первое заключение!")
            return
            
        total_tickets, total_value, points, rank, achievements_json = row
        achievements = json.loads(achievements_json or '[]')
        
        ach_text = "\n".join([f"• {a}" for a in achievements]) if achievements else "<i>Пока нет наград</i>"
        
        how_it_works = (
            f"💡 <b>КАК ЭТО РАБОТАЕТ?</b>\n"
            f"• <b>+10 баллов</b> за каждое заключение\n"
            f"• <b>+1 балл</b> за каждые 1000 ₽ суммы оценки\n\n"
            f"📈 <b>УРОВНИ:</b>\n"
            f"🥉 Новичок (0+)\n"
            f"🥈 Ученик (50+)\n"
            f"🥇 Стажер (150+)\n"
            f"🎖 Специалист (400+)\n"
            f"🏆 Мастер (1000+)\n"
            f"🚀 Профи (2500+)\n"
            f"💎 Эксперт (5000+)\n"
            f"👑 Легенда (10000+)"
        )
        
        text = (
            f"📊 <b>ВАША СТАТИСТИКА</b>\n\n"
            f"👤 <b>{user.full_name}</b>\n"
            f"🎖 Ранг: <b>{rank}</b>\n"
            f"⭐ Баллы опыта: <b>{points}</b>\n\n"
            f"💼 Обработано заключений: <b>{total_tickets}</b>\n"
            f"💰 Общая сумма оценки: <b>{total_value:,} ₽</b>\n\n"
            f"🏅 <b>НАГРАДЫ:</b>\n"
            f"{ach_text}\n\n"
            f"{how_it_works}"
        )
        
        await safe_reply(update, text, parse_mode="HTML")
        
    except Exception as e:
        logger.error(f"Stats command error: {e}")
        await safe_reply(update, "❌ Ошибка получения статистики.")
