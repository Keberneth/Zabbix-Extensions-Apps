# logging_utils.py
from __future__ import annotations

import json
import logging
import logging.handlers
from pathlib import Path
from typing import List

from .config import DATA_DIR, LOG_DIR  # LOG_DIR added in config.py


LOG_FILE: Path = LOG_DIR / "app.log"
SETTINGS_FILE: Path = DATA_DIR / "logging_settings.json"

DEFAULT_LEVEL_NAME = "ERROR"
MAX_LOG_LINES = 5000


def _parse_level(level: str | int | None) -> int:
    if isinstance(level, int):
        return level
    if not isinstance(level, str):
        return logging.getLevelName(DEFAULT_LEVEL_NAME)
    lvl = getattr(logging, level.upper(), None)
    if isinstance(lvl, int):
        return lvl
    return getattr(logging, DEFAULT_LEVEL_NAME, logging.ERROR)


def _level_name(level: int) -> str:
    name = logging.getLevelName(level)
    if isinstance(name, str):
        return name
    return DEFAULT_LEVEL_NAME


def _load_level_from_settings() -> str:
    if not SETTINGS_FILE.exists():
        return DEFAULT_LEVEL_NAME
    try:
        with SETTINGS_FILE.open("r", encoding="utf-8") as f:
            data = json.load(f)
        level = str(data.get("level", DEFAULT_LEVEL_NAME))
        return level.upper()
    except Exception:
        return DEFAULT_LEVEL_NAME


def _save_level_to_settings(level_name: str) -> None:
    data = {"level": level_name.upper()}
    try:
        with SETTINGS_FILE.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception:
        # Logging must not crash on settings write errors
        pass


def setup_logging() -> logging.Logger:
    """
    Configure a rotating file logger for the whole app.

    - Default level: ERROR
    - Rotates at ~5 MB, keeps 5 backups
    """
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger()
    if getattr(root, "_zabbix_report_configured", False):
        return root

    # Load level from settings (or default)
    level_name = _load_level_from_settings()
    level = _parse_level(level_name)

    root.setLevel(level)

    handler = logging.handlers.RotatingFileHandler(
        LOG_FILE,
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    handler.setLevel(level)

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s - %(message)s"
    )
    handler.setFormatter(fmt)

    root.addHandler(handler)

    # Make uvicorn / fastapi loggers propagate into root
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access", "fastapi"):
        logging.getLogger(name).propagate = True

    root._zabbix_report_configured = True  # type: ignore[attr-defined]
    return root


def get_log_level() -> str:
    root = logging.getLogger()
    return _level_name(root.level)


def set_log_level(level_name: str) -> str:
    """
    Change log level at runtime for root and all existing handlers,
    and persist the choice.
    """
    root = logging.getLogger()
    level = _parse_level(level_name)
    root.setLevel(level)

    for h in root.handlers:
        h.setLevel(level)

    name = _level_name(level)
    _save_level_to_settings(name)
    return name


def tail_log(max_lines: int = 200) -> List[str]:
    """
    Return the last `max_lines` lines of the main log file.

    - Hard-capped at MAX_LOG_LINES for safety
    - Handles large files efficiently (backwards read)
    """
    if not LOG_FILE.exists():
        return []

    try:
        n = int(max_lines)
    except (TypeError, ValueError):
        n = 200

    n = max(1, min(MAX_LOG_LINES, n))

    lines: List[bytes] = []

    with LOG_FILE.open("rb") as f:
        f.seek(0, 2)
        file_size = f.tell()
        block_size = 4096

        buf = b""
        pos = file_size

        while pos > 0 and len(lines) <= n:
            read_size = block_size if pos >= block_size else pos
            pos -= read_size
            f.seek(pos)
            data = f.read(read_size)
            buf = data + buf
            lines = buf.splitlines()

        # Take only the last n lines
        last = lines[-n:]
        return [l.decode("utf-8", errors="replace") for l in last]

