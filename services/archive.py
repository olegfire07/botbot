import asyncio
import shutil
import json
import zipfile
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional
from config.settings import settings
from utils.helpers import parse_date_str, sanitize_filename
import logging

logger = logging.getLogger(__name__)
archive_lock = asyncio.Lock()

def _read_archive_index() -> List[Dict[str, Any]]:
    if not settings.ARCHIVE_INDEX_FILE.exists():
        return []
    try:
        with settings.ARCHIVE_INDEX_FILE.open("r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logger.warning(f"Failed to read archive index: {e}")
        return []

def _write_archive_index(entries: List[Dict[str, Any]]) -> None:
    settings.ARCHIVE_INDEX_FILE.parent.mkdir(parents=True, exist_ok=True)
    with settings.ARCHIVE_INDEX_FILE.open("w", encoding="utf-8") as f:
        json.dump(entries, f, ensure_ascii=False, indent=2)

async def archive_document(filepath: Path, data: Dict[str, Any]) -> Optional[Path]:
    if not filepath.is_file():
        return None

    date_text = data.get("date")
    dt = parse_date_str(date_text)
    subdir_name = dt.strftime("%Y-%m") if dt else "undated"
    month_dir = settings.ARCHIVE_DIR / subdir_name

    description = data.get('photo_desc', [])

    def _copy_and_index() -> Optional[Path]:
        month_dir.mkdir(parents=True, exist_ok=True)
        target = month_dir / filepath.name
        counter = 1
        while target.exists():
            target = month_dir / f"{filepath.stem}_{counter}{filepath.suffix}"
            counter += 1
        shutil.copy2(filepath, target)

        entry = {
            "archive_path": str(target.relative_to(settings.ARCHIVE_DIR)),
            "date": date_text,
            "department_number": data.get("department_number"),
            "issue_number": data.get("issue_number"),
            "ticket_number": data.get("ticket_number"),
            "region": data.get("region"),
            "items": description,
            "created_at": datetime.now().isoformat(timespec="seconds"),
        }

        entries = _read_archive_index()
        entries.append(entry)
        _write_archive_index(entries)
        return target

    async with archive_lock:
        return await asyncio.to_thread(_copy_and_index)

async def get_archive_paths(start_date: datetime, end_date: datetime, region: Optional[str]) -> List[Path]:
    async with archive_lock:
        entries = await asyncio.to_thread(_read_archive_index)

    paths: List[Path] = []
    for entry in entries:
        entry_date = parse_date_str(entry.get("date"))
        if not entry_date:
            continue
        if entry_date < start_date or entry_date > end_date:
            continue
        entry_region = entry.get("region")
        if region and entry_region != region:
            continue
        rel_path = entry.get("archive_path")
        if not rel_path:
            continue
        abs_path = settings.ARCHIVE_DIR / rel_path
        if abs_path.is_file():
            paths.append(abs_path)
    return paths

async def create_zip_archive(paths: List[Path], filename: str) -> Path:
    settings.DOCS_DIR.mkdir(parents=True, exist_ok=True)
    zip_path = settings.DOCS_DIR / filename
    
    def _zip():
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for path in paths:
                zf.write(path, arcname=path.name)
        return zip_path

    return await asyncio.to_thread(_zip)
