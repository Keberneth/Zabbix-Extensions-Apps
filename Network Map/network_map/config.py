"""Application-wide constants and filesystem paths.

Important: URLs, API keys, and feature flags are NOT stored here anymore.
They are stored in /etc/network-map/settings.json and managed via /admin.

This module must be safe to import even when the application is not configured.
"""

from __future__ import annotations

import os
import ipaddress
import warnings
from pathlib import Path

import urllib3

# --- Installation / filesystem layout ---

# Where the application is installed (used for logs/data/reports).
# Default matches the provided systemd + nginx examples.
INSTALL_DIR = Path(os.environ.get("NETWORK_MAP_INSTALL_DIR", "/opt/network_map"))

STATIC_DIR = INSTALL_DIR / "static"  # served by nginx
REPORT_DIR = Path(os.environ.get("NETWORK_MAP_REPORT_DIR", str(INSTALL_DIR / "reports")))
DATA_DIR = Path(os.environ.get("NETWORK_MAP_DATA_DIR", str(INSTALL_DIR / "data")))
LOG_DIR = Path(os.environ.get("NETWORK_MAP_LOG_DIR", str(INSTALL_DIR / "logs")))

# Where settings/secrets live
SETTINGS_DIR = Path(os.environ.get("NETWORK_MAP_SETTINGS_DIR", "/etc/network-map"))
SETTINGS_FILE = Path(os.environ.get("NETWORK_MAP_SETTINGS_FILE", str(SETTINGS_DIR / "settings.json")))
SECRET_KEY_FILE = Path(os.environ.get("NETWORK_MAP_SECRET_KEY_FILE", str(SETTINGS_DIR / "secret.key")))
ADMIN_PASSWORD_FILE = Path(
    os.environ.get("NETWORK_MAP_ADMIN_PASSWORD_FILE", str(SETTINGS_DIR / "admin_password.txt"))
)

# --- Default refresh intervals ---

DEFAULT_ZABBIX_SYNC_SECONDS = int(os.environ.get("NETWORK_MAP_ZABBIX_SYNC_SECONDS", "1800"))  # 30 min
DEFAULT_NETBOX_SYNC_SECONDS = int(os.environ.get("NETWORK_MAP_NETBOX_SYNC_SECONDS", "86400"))  # 24h
DEFAULT_REPORT_SYNC_SECONDS = int(os.environ.get("NETWORK_MAP_REPORT_SYNC_SECONDS", "86400"))  # 24h

# --- IP ranges / colors ---

PRIVATE_NETWORKS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("172.16.0.0/12"),
]

ENV_COLOR_MAP = {
    "prod": "#007bff",
    "dev": "#28a745",
    "test": "#fd7e14",
    "qa": "#6f42c1",
    "unknown": "#6c757d",
    "external": "#ff3366",
    "internal-unknown": "#999999",
}

# Keep ignoring certificate warnings as before
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# SubjectAltNameWarning exists only in older urllib3; make it optional
SubjectAltNameWarning = getattr(urllib3.exceptions, "SubjectAltNameWarning", None)
if SubjectAltNameWarning is not None:
    warnings.simplefilter("ignore", SubjectAltNameWarning)
