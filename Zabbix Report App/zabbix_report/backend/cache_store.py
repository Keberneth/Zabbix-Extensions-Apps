# cache_store.py
import json
import time
from pathlib import Path
from typing import Any, Dict, Optional

from .config import CACHE_DIR  # uses /otp/zabbix_report/data/cache :contentReference[oaicite:1]{index=1}

def _safe_name(name: str) -> str:
    return "".join(c for c in name if c.isalnum() or c in "-_.")[:80] or "cache"

def _cache_path(name: str) -> Path:
    return CACHE_DIR / f"{_safe_name(name)}.json"

def load_cache(name: str, default: Any = None) -> Any:
    """
    Load a JSON cache file. Returns `default` if missing or invalid.
    """
    path = _cache_path(name)
    if not path.exists():
        return default
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default

def save_cache(name: str, data: Any) -> None:
    """
    Save JSON data atomically to the cache file.
    """
    path = _cache_path(name)
    tmp = path.with_suffix(".json.tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, sort_keys=True)
    tmp.replace(path)

def touch_cache(name: str) -> None:
    """
    Track last update time for a cache.
    """
    meta_name = f"{name}.__meta"
    path = _cache_path(meta_name)
    data = {"updated_at": int(time.time())}
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f)

def get_cache_age_seconds(name: str) -> Optional[int]:
    """
    Return seconds since last touch_cache(name), or None if no meta exists.
    """
    meta_name = f"{name}.__meta"
    path = _cache_path(meta_name)
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return int(time.time()) - int(data.get("updated_at", 0))
    except Exception:
        return None
