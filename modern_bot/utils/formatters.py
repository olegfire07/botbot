from typing import List, Any

def format_history_record(record: List[Any]) -> str:
    """Format a single history record into a readable string."""
    ticket = record[0] if len(record) > 0 else "?"
    num = record[1] if len(record) > 1 else "?"
    dept = record[2] if len(record) > 2 else "?"
    date = record[3] if len(record) > 3 else "?"
    region = record[4] if len(record) > 4 else "?"
    rating = record[7] if len(record) > 7 else "?"
    
    return (
        f"• <b>Билет:</b> {ticket}, <b>№:</b> {num}\n"
        f"  <b>Под:</b> {dept}, <b>Дата:</b> {date}\n"
        f"  <b>Регион:</b> {region}, <b>Оценка:</b> {rating}\n"
    )

def format_history_list(records: List[List[Any]], limit: int = 10) -> str:
    """Format a list of history records."""
    if not records:
        return "📜 <b>История</b>\n\nИстория пуста."
        
    text = f"📜 <b>Последние {min(len(records), limit)} записей:</b>\n\n"
    for r in records[-limit:]:
        text += format_history_record(r) + "\n"
    return text
