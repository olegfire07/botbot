import logging
from datetime import datetime, timedelta
from collections import Counter
from typing import Dict, List, Any
from modern_bot.services.excel import read_excel_data
from modern_bot.utils.validators import parse_date_str

logger = logging.getLogger(__name__)

class AnalyticsService:
    """Service for generating analytics reports."""
    
    @staticmethod
    async def get_region_stats(days: int = 30) -> Dict[str, int]:
        """Get statistics by region."""
        rows = await read_excel_data()
        if not rows:
            return {}
            
        # Region is index 4
        stats = Counter(row[4] for row in rows if len(row) > 4 and row[4])
        return dict(stats)
    
    @staticmethod
    async def get_department_stats(days: int = 30) -> Dict[str, int]:
        """Get statistics by department."""
        rows = await read_excel_data()
        if not rows:
            return {}
            
        # Department is index 2
        stats = Counter(str(row[2]) for row in rows if len(row) > 2 and row[2])
        return dict(stats)
    
    @staticmethod
    async def get_top_users(limit: int = 10) -> List[Dict[str, Any]]:
        """Get top users by submission count."""
        rows = await read_excel_data()
        if not rows:
            return []
            
        # User is index 8 (added recently)
        # We need to be careful about rows created before this column existed
        users = []
        for row in rows:
            if len(row) > 8 and row[8]:
                users.append(str(row[8]))
                
        stats = Counter(users)
        return [{"user": user, "count": count} for user, count in stats.most_common(limit)]
    
    @staticmethod
    async def get_daily_stats(days: int = 30) -> Dict[str, int]:
        """Get daily document creation statistics."""
        rows = await read_excel_data()
        if not rows:
            return {}
            
        stats = Counter()
        cutoff = datetime.now() - timedelta(days=days)
        
        for row in rows:
            if len(row) > 3 and row[3]:
                dt = parse_date_str(row[3])
                if dt and dt >= cutoff:
                    stats[dt.strftime("%d.%m")] += 1
                    
        # Sort by date
        return dict(sorted(stats.items(), key=lambda x: datetime.strptime(x[0] + f".{datetime.now().year}", "%d.%m.%Y"), reverse=True))
    
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
            return "👥 <b>Топ пользователей</b>\n\nНет данных (возможно, новые заключения еще не создавались)."
            
        lines = ["👥 <b>Топ активных пользователей</b>\n"]
        for i, u in enumerate(users, 1):
            name = u['user']
            count = u['count']
            icon = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else "👤"
            lines.append(f"{icon} <b>{name}</b>: {count} зак.")
            
        return "\n".join(lines)
    
    @staticmethod
    def create_simple_chart(data: Dict[str, int], width: int = 20) -> str:
        """Create simple ASCII chart."""
        if not data:
            return "Нет данных за последние 30 дней."
        
        max_val = max(data.values()) if data.values() else 1
        lines = []
        
        for key, value in list(data.items())[:15]:  # Show last 15 days
            bar_length = int((value / max_val) * width) if max_val > 0 else 0
            bar = "█" * bar_length
            lines.append(f"<code>{key}</code> {bar} {value}")
        
        return "\n".join(lines)

    @staticmethod
    async def get_period_stats(start_date: datetime, end_date: datetime) -> Dict[str, Any]:
        """Get statistics for a specific period."""
        rows = await read_excel_data()
        if not rows:
            return {}
            
        total_count = 0
        region_stats = Counter()
        dept_stats = Counter()
        
        # Ensure end_date covers the whole day
        end_date = end_date.replace(hour=23, minute=59, second=59)
        
        for row in rows:
            if len(row) > 3 and row[3]:
                dt = parse_date_str(row[3])
                if dt and start_date <= dt <= end_date:
                    total_count += 1
                    if len(row) > 4 and row[4]:
                        region_stats[row[4]] += 1
                    if len(row) > 2 and row[2]:
                        dept_stats[str(row[2])] += 1
                        
        return {
            "total": total_count,
            "regions": dict(region_stats),
            "departments": dict(dept_stats)
        }

    @staticmethod
    def format_period_report(stats: Dict[str, Any], start: datetime, end: datetime) -> str:
        """Format period statistics report."""
        if not stats or stats.get("total", 0) == 0:
            return f"📊 <b>Отчет за период</b>\n{start.strftime('%d.%m.%Y')} - {end.strftime('%d.%m.%Y')}\n\nНет данных."
            
        lines = [
            f"📊 <b>Отчет за период</b>",
            f"📅 {start.strftime('%d.%m.%Y')} - {end.strftime('%d.%m.%Y')}",
            f"\n<b>Всего заключений:</b> {stats['total']}\n",
            "<b>По регионам:</b>"
        ]
        
        for region, count in sorted(stats['regions'].items(), key=lambda x: x[1], reverse=True):
            lines.append(f"• {region}: {count}")
            
        lines.append("\n<b>По подразделениям (топ 5):</b>")
        for dept, count in sorted(stats['departments'].items(), key=lambda x: x[1], reverse=True)[:5]:
            lines.append(f"• {dept}: {count}")
            
        return "\n".join(lines)
