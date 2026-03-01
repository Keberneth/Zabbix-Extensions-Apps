import os
import time
import ipaddress

from config import REPORT_DIR
from settings_store import get_effective_settings, EffectiveSettings

# Output and cache
OUTPUT_DIR = str(REPORT_DIR)
os.makedirs(OUTPUT_DIR, exist_ok=True)

CACHE_DIR = os.path.join(OUTPUT_DIR, "cache")
os.makedirs(CACHE_DIR, exist_ok=True)

# Sliding window config
DAYS = 30
HISTORY_CHUNK = 24 * 3600  # 1 day

# Cache refresh behaviour
CACHE_REFRESH_DAYS = 2


def current_time_window():
    """Return (time_from, time_till) for the current rolling 30-day window."""
    now = int(time.time())
    return now - DAYS * 24 * 3600, now


# Hosts to exclude in DrawIO
EXCLUDED_HOSTS = {"Zabbix server"}


def get_netbox_headers(settings: EffectiveSettings | None = None):
    """Return NetBox headers for report generation.

    Returns None if NetBox is disabled or not configured.
    """
    settings = settings or get_effective_settings()
    if not settings.enable_netbox:
        return None
    if not settings.netbox_token:
        return None
    return {
        "Authorization": f"Token {settings.netbox_token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


# Internal IP ranges
INTERNAL_NETWORKS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("172.16.0.0/12"),
]
