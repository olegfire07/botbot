import asyncio
import atexit
import logging
import os
import re
import shutil
from pathlib import Path
from typing import Optional

from modern_bot.config import API_PORT, BASE_DIR

logger = logging.getLogger(__name__)

_tunnel_process = None
_tunnel_url = None
_tunnel_monitor_task = None
_tunnel_lock = None
_tunnel_atexit_registered = False

_URL_REGEX = re.compile(r"https://(?!api\.)[a-z0-9-]+\.trycloudflare\.com", re.IGNORECASE)


def _should_start_auto_tunnel() -> bool:
    value = os.getenv("AUTO_TUNNEL", "").strip().lower()
    if value in {"0", "false", "off", "no"}:
        return False
    if value in {"1", "true", "on", "yes"}:
        return True

    bot_url = os.getenv("BOT_URL", "").strip().lower()
    if not bot_url:
        return True
    if "trycloudflare.com" in bot_url:
        return True
    return "127.0.0.1" in bot_url or "localhost" in bot_url


def _find_cloudflared() -> Optional[str]:
    env_path = os.getenv("CLOUDFLARED_PATH", "").strip()
    if env_path and Path(env_path).exists():
        return env_path

    exe_name = "cloudflared.exe" if os.name == "nt" else "cloudflared"
    found = shutil.which(exe_name)
    if found:
        return found

    candidates = [
        BASE_DIR / "bin" / exe_name,
        BASE_DIR / exe_name,
        Path(__file__).resolve().parent.parent / "bin" / exe_name,
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return None


async def _read_tunnel_url(process: asyncio.subprocess.Process, timeout_seconds: int = 25) -> Optional[str]:
    if not process.stdout:
        return None

    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout_seconds

    while loop.time() < deadline:
        try:
            line = await asyncio.wait_for(process.stdout.readline(), timeout=1.0)
        except asyncio.TimeoutError:
            if process.returncode is not None:
                return None
            continue

        if not line:
            break
        text = line.decode(errors="ignore").strip()
        logger.debug("AUTO_TUNNEL: %s", text)
        match = _URL_REGEX.search(text)
        if match:
            return match.group(0)
    return None


def _cleanup_tunnel() -> None:
    global _tunnel_process
    if _tunnel_process and _tunnel_process.returncode is None:
        try:
            _tunnel_process.terminate()
        except Exception:
            return


def _get_tunnel_lock() -> asyncio.Lock:
    global _tunnel_lock
    if _tunnel_lock is None:
        _tunnel_lock = asyncio.Lock()
    return _tunnel_lock


def _tunnel_is_alive() -> bool:
    return _tunnel_process is not None and _tunnel_process.returncode is None


async def _start_cloudflared(port: int) -> Optional[str]:
    global _tunnel_process, _tunnel_url, _tunnel_atexit_registered

    if _tunnel_is_alive() and _tunnel_url:
        return _tunnel_url

    cloudflared_path = _find_cloudflared()
    if not cloudflared_path:
        logger.warning("AUTO_TUNNEL: cloudflared not found. Install it or set BOT_URL manually.")
        return None

    cmd = [
        cloudflared_path,
        "tunnel",
        "--url",
        f"http://127.0.0.1:{port}",
        "--no-autoupdate",
        "--protocol",
        "http2",
        "--edge-ip-version",
        "4",
    ]

    logger.info("AUTO_TUNNEL: starting cloudflared...")
    _tunnel_process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    if not _tunnel_atexit_registered:
        atexit.register(_cleanup_tunnel)
        _tunnel_atexit_registered = True

    _tunnel_url = await _read_tunnel_url(_tunnel_process)
    if not _tunnel_url:
        logger.warning("AUTO_TUNNEL: failed to detect public URL.")
        return None

    os.environ["BOT_URL"] = _tunnel_url
    logger.info("AUTO_TUNNEL: public URL set to %s", _tunnel_url)
    return _tunnel_url


async def _monitor_tunnel(port: int) -> None:
    global _tunnel_url
    backoff = 2
    while True:
        await asyncio.sleep(2)
        if _tunnel_is_alive():
            continue

        if not _should_start_auto_tunnel():
            return

        exit_code = None
        if _tunnel_process is not None:
            exit_code = _tunnel_process.returncode
        if exit_code is not None:
            logger.warning("AUTO_TUNNEL: cloudflared exited with code %s. Restarting...", exit_code)

        async with _get_tunnel_lock():
            _tunnel_url = None
            await _start_cloudflared(port)

        if _tunnel_url:
            backoff = 2
        else:
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 60)


async def start_auto_tunnel(port: Optional[int] = None) -> Optional[str]:
    global _tunnel_url, _tunnel_monitor_task

    if _tunnel_url:
        return _tunnel_url

    if not _should_start_auto_tunnel():
        return None

    if os.getenv("BOT_URL", "").strip():
        return os.getenv("BOT_URL").strip()

    port = port or API_PORT
    async with _get_tunnel_lock():
        await _start_cloudflared(port)

    if not _tunnel_monitor_task or _tunnel_monitor_task.done():
        _tunnel_monitor_task = asyncio.create_task(_monitor_tunnel(port))

    return _tunnel_url
