import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional

from modern_bot.config import DATA_RETENTION_DAYS
from modern_bot.database.db import get_setting, set_setting, prune_old_records
from modern_bot.services.archive import prune_archive_index
from modern_bot.services.excel import prune_excel_data
from modern_bot.utils.files import clean_old_archives

logger = logging.getLogger(__name__)


def get_retention_cutoff() -> datetime:
    return datetime.now() - timedelta(days=DATA_RETENTION_DAYS)


async def get_effective_cutoff() -> datetime:
    cutoff = get_retention_cutoff()
    reset_raw = await get_setting("stats_reset_at", "")
    if reset_raw:
        reset_dt = _parse_reset_date(reset_raw)
        if reset_dt:
            cutoff = max(cutoff, reset_dt)
    return cutoff


async def set_stats_reset_now() -> str:
    now = datetime.now().replace(microsecond=0)
    await set_setting("stats_reset_at", now.isoformat())
    return now.isoformat()


def _parse_reset_date(value: str) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


async def run_retention_cleanup() -> Dict[str, Any]:
    cutoff = get_retention_cutoff()
    summary: Dict[str, Any] = {"cutoff": cutoff.isoformat(timespec="seconds")}

    try:
        summary["excel_rows"] = await prune_excel_data(cutoff)
    except Exception as exc:
        logger.error("Retention cleanup: excel prune failed: %s", exc)
        summary["excel_rows"] = None

    try:
        summary["db"] = await prune_old_records(cutoff)
    except Exception as exc:
        logger.error("Retention cleanup: DB prune failed: %s", exc)
        summary["db"] = None

    try:
        summary["archives_removed"] = await prune_archive_index(cutoff)
    except Exception as exc:
        logger.error("Retention cleanup: archive index prune failed: %s", exc)
        summary["archives_removed"] = None

    await asyncio.to_thread(clean_old_archives)
    return summary
