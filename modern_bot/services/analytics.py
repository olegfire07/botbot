import logging
from datetime import datetime, timedelta
from pathlib import Path
from collections import Counter, defaultdict
from typing import Dict, List, Any
from modern_bot.config import DOCS_DIR

logger = logging.getLogger(__name__)

class AnalyticsService:
    """Service for generating analytics reports."""
    
    @staticmethod
    async def get_region_stats(days: int = 30) -> Dict[str, int]:
        """Get statistics by region for the last N days."""
        # TODO: Implement database query
        # For now, return mock data
        return {
            "Москва": 45,
            "Санкт-Петербург": 32,
            "Екатеринбург": 28,
            "Новосибирск": 15,
            "Казань": 12
        }
    
    @staticmethod
    async def get_department_stats(days: int = 30) -> Dict[str, int]:
        """Get statistics by department for the last N days."""
        # TODO: Implement database query
        return {
            "385": 67,
            "350": 45,
            "420": 38,
            "510": 22,
            "670": 18
        }
    
    @staticmethod
    async def get_top_users(limit: int = 10) -> List[Dict[str, Any]]:
        """Get top users by number of documents created."""
        # TODO: Implement database query
        return [
            {"user_id": 123456, "username": "Иван", "count": 45},
            {"user_id": 234567, "username": "Мария", "count": 38},
            {"user_id": 345678, "username": "Петр", "count": 32},
            {"user_id": 456789, "username": "Ольга", "count": 28},
            {"user_id": 567890, "username": "Алексей", "count": 25}
        ]
    
    @staticmethod
    async def get_daily_stats(days: int = 30) -> Dict[str, int]:
        """Get daily document creation statistics."""
        # TODO: Implement database query
        today = datetime.now()
        stats = {}
        for i in range(days):
            date = (today - timedelta(days=i)).strftime("%d.%m")
            stats[date] = max(0, 20 + (i % 7) * 3 - i // 7)
        return dict(reversed(list(stats.items())))
    
    @staticmethod
    def format_region_report(stats: Dict[str, int]) -> str:
        """Format region statistics as text report."""
        if not stats:
            return "📊 Нет данных"
        
        total = sum(stats.values())
        lines = ["📊 <b>Статистика по регионам</b>\n"]
        
        for region, count in sorted(stats.items(), key=lambda x: x[1], reverse=True):
            percentage = (count / total * 100) if total > 0 else 0
            bar = "█" * int(percentage / 5)
            lines.append(f"<code>{region:20s}</code> {count:3d} ({percentage:4.1f}%) {bar}")
        
        lines.append(f"\n<b>Всего:</b> {total}")
        return "\n".join(lines)
    
    @staticmethod
    def format_department_report(stats: Dict[str, int]) -> str:
        """Format department statistics as text report."""
        if not stats:
            return "📊 Нет данных"
        
        total = sum(stats.values())
        lines = ["📊 <b>Статистика по подразделениям</b>\n"]
        
        for dept, count in sorted(stats.items(), key=lambda x: x[1], reverse=True):
            percentage = (count / total * 100) if total > 0 else 0
            bar = "█" * int(percentage / 5)
            lines.append(f"<code>Подр. {dept:10s}</code> {count:3d} ({percentage:4.1f}%) {bar}")
        
        lines.append(f"\n<b>Всего:</b> {total}")
        return "\n".join(lines)
    
    @staticmethod
    def format_top_users_report(users: List[Dict[str, Any]]) -> str:
        """Format top users report."""
        if not users:
            return "👥 Нет данных"
        
        lines = ["👥 <b>Топ пользователей</b>\n"]
        
        medals = ["🥇", "🥈", "🥉"]
        for i, user in enumerate(users[:10]):
            medal = medals[i] if i < 3 else f"{i+1}."
            username = user.get("username", "Неизвестно")
            count = user.get("count", 0)
            lines.append(f"{medal} <b>{username}</b> — {count} документов")
        
        return "\n".join(lines)
    
    @staticmethod
    def create_simple_chart(data: Dict[str, int], width: int = 30) -> str:
        """Create simple ASCII chart."""
        if not data:
            return ""
        
        max_val = max(data.values()) if data.values() else 1
        lines = []
        
        for key, value in list(data.items())[:10]:  # Show last 10
            bar_length = int((value / max_val) * width) if max_val > 0 else 0
            bar = "█" * bar_length
            lines.append(f"<code>{key:10s}</code> {bar} {value}")
        
        return "\n".join(lines)
