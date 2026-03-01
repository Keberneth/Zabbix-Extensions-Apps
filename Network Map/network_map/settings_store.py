"""Settings persistence for Network Map.

Settings are stored in JSON on disk (default: /etc/network-map/settings.json).
Secrets (API tokens) are stored encrypted.

This module is designed so the application can start even with missing settings.
"""

from __future__ import annotations

import json
import os
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from config import (
    SETTINGS_FILE,
    SETTINGS_DIR,
    DEFAULT_NETBOX_SYNC_SECONDS,
    DEFAULT_REPORT_SYNC_SECONDS,
    DEFAULT_ZABBIX_SYNC_SECONDS,
)
from crypto_utils import encrypt_str, decrypt_str
from log import get_logger

logger = get_logger(__name__)

_SETTINGS_LOCK = threading.Lock()
_SETTINGS_CACHE: Optional[Dict[str, Any]] = None


@dataclass(frozen=True)
class EffectiveSettings:
    # URLs
    zabbix_url: str
    netbox_url: str

    # Plaintext tokens (decrypted)
    zabbix_token: str
    netbox_token: str

    # Feature flags
    enable_netbox: bool

    # Intervals
    zabbix_sync_seconds: int
    netbox_sync_seconds: int
    report_sync_seconds: int

    # Admin auth
    admin_password_hash: str
    session_secret: str


def _now_iso() -> str:
    return datetime.utcnow().isoformat() + "Z"


def _defaults() -> Dict[str, Any]:
    return {
        "zabbix_url": "",
        "zabbix_token_enc": "",
        "netbox_url": "",
        "netbox_token_enc": "",
        "enable_netbox": True,
        "zabbix_sync_seconds": int(DEFAULT_ZABBIX_SYNC_SECONDS),
        "netbox_sync_seconds": int(DEFAULT_NETBOX_SYNC_SECONDS),
        "report_sync_seconds": int(DEFAULT_REPORT_SYNC_SECONDS),
        # Auth
        "admin_password_hash": "",
        "session_secret": "",
        # Metadata
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
    }


def _read_json_file(path: Path) -> Dict[str, Any]:
    try:
        if not path.exists():
            return {}
        raw = path.read_text(encoding="utf-8")
        if not raw.strip():
            return {}
        data = json.loads(raw)
        if isinstance(data, dict):
            return data
        return {}
    except Exception as e:
        logger.warning("Failed to read settings file %s: %s", path, e)
        return {}


def _write_json_file_atomic(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    try:
        tmp.chmod(0o600)
    except Exception:
        pass

    tmp.replace(path)

    # Best-effort secure perms on settings dir
    try:
        Path(SETTINGS_DIR).chmod(0o700)
    except Exception:
        pass


def load_settings(force_reload: bool = False) -> Dict[str, Any]:
    """Load settings from disk (cached)."""
    global _SETTINGS_CACHE
    with _SETTINGS_LOCK:
        if _SETTINGS_CACHE is not None and not force_reload:
            return dict(_SETTINGS_CACHE)

        path = Path(SETTINGS_FILE)
        data = _defaults()
        file_data = _read_json_file(path)
        data.update(file_data)

        # Ensure required keys exist
        for k, v in _defaults().items():
            data.setdefault(k, v)

        _SETTINGS_CACHE = dict(data)
        return dict(_SETTINGS_CACHE)


def save_settings(new_data: Dict[str, Any]) -> Dict[str, Any]:
    """Persist settings to disk and update cache.

    Expects *encrypted* tokens in fields ending with _enc.
    """
    global _SETTINGS_CACHE
    with _SETTINGS_LOCK:
        cur = load_settings(force_reload=True)
        merged = dict(cur)
        merged.update(new_data)
        merged["updated_at"] = _now_iso()

        path = Path(SETTINGS_FILE)
        _write_json_file_atomic(path, merged)
        _SETTINGS_CACHE = dict(merged)
        return dict(_SETTINGS_CACHE)


def update_credentials(
    *,
    zabbix_url: Optional[str] = None,
    zabbix_token_plain: Optional[str] = None,
    netbox_url: Optional[str] = None,
    netbox_token_plain: Optional[str] = None,
) -> Dict[str, Any]:
    """Convenience updater that encrypts tokens before saving."""
    payload: Dict[str, Any] = {}
    if zabbix_url is not None:
        payload["zabbix_url"] = zabbix_url
    if zabbix_token_plain is not None:
        payload["zabbix_token_enc"] = encrypt_str(zabbix_token_plain) if zabbix_token_plain else ""
    if netbox_url is not None:
        payload["netbox_url"] = netbox_url
    if netbox_token_plain is not None:
        payload["netbox_token_enc"] = encrypt_str(netbox_token_plain) if netbox_token_plain else ""
    return save_settings(payload)


def get_effective_settings() -> EffectiveSettings:
    """Return settings with decrypted tokens and env-var fallback.

    Precedence:
      1) settings.json values (including encrypted tokens)
      2) environment variables (NETWORK_MAP_*), only when the settings value is empty
      3) defaults

    This makes it possible to start with env vars but later move to /admin-managed settings.
    """
    s = load_settings()

    def env(name: str) -> str:
        return os.environ.get(name, "").strip()

    zabbix_url = (s.get("zabbix_url") or "").strip() or env("NETWORK_MAP_ZABBIX_URL")
    netbox_url = (s.get("netbox_url") or "").strip() or env("NETWORK_MAP_NETBOX_URL")

    zabbix_token = decrypt_str(s.get("zabbix_token_enc") or "") or env("NETWORK_MAP_ZABBIX_TOKEN")
    netbox_token = decrypt_str(s.get("netbox_token_enc") or "") or env("NETWORK_MAP_NETBOX_TOKEN")

    enable_netbox = bool(s.get("enable_netbox", True))

    # Intervals
    def _int(name: str, default: int) -> int:
        try:
            v = int(s.get(name, default))
            return max(1, v)
        except Exception:
            return default

    zabbix_sync = _int("zabbix_sync_seconds", int(DEFAULT_ZABBIX_SYNC_SECONDS))
    netbox_sync = _int("netbox_sync_seconds", int(DEFAULT_NETBOX_SYNC_SECONDS))
    report_sync = _int("report_sync_seconds", int(DEFAULT_REPORT_SYNC_SECONDS))

    admin_hash = str(s.get("admin_password_hash") or "")
    session_secret = str(s.get("session_secret") or "")

    return EffectiveSettings(
        zabbix_url=zabbix_url,
        netbox_url=netbox_url,
        zabbix_token=zabbix_token,
        netbox_token=netbox_token,
        enable_netbox=enable_netbox,
        zabbix_sync_seconds=zabbix_sync,
        netbox_sync_seconds=netbox_sync,
        report_sync_seconds=report_sync,
        admin_password_hash=admin_hash,
        session_secret=session_secret,
    )


def masked_settings_for_ui() -> Dict[str, Any]:
    """Settings payload safe to send to the admin UI.

    Tokens are never returned decrypted. Instead we return booleans telling if they are set.
    """
    s = load_settings()
    return {
        "zabbix_url": (s.get("zabbix_url") or ""),
        "zabbix_token_set": bool(s.get("zabbix_token_enc")),
        "netbox_url": (s.get("netbox_url") or ""),
        "netbox_token_set": bool(s.get("netbox_token_enc")),
        "enable_netbox": bool(s.get("enable_netbox", True)),
        "zabbix_sync_seconds": int(s.get("zabbix_sync_seconds", int(DEFAULT_ZABBIX_SYNC_SECONDS))),
        "netbox_sync_seconds": int(s.get("netbox_sync_seconds", int(DEFAULT_NETBOX_SYNC_SECONDS))),
        "report_sync_seconds": int(s.get("report_sync_seconds", int(DEFAULT_REPORT_SYNC_SECONDS))),
        "updated_at": s.get("updated_at"),
        "created_at": s.get("created_at"),
    }
