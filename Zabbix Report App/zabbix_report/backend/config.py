from pathlib import Path
import os

# Base application paths
APP_ROOT = Path("/opt/zabbix_report").resolve()

DATA_DIR = APP_ROOT / "data"
CACHE_DIR = DATA_DIR / "cache"
TMP_DIR = DATA_DIR / "tmp"
LOG_DIR = DATA_DIR / "logs"

# Create all needed directories
for d in (DATA_DIR, CACHE_DIR, TMP_DIR, LOG_DIR):
    d.mkdir(parents=True, exist_ok=True)

# Zabbix environment variables
ZABBIX_URL = os.getenv("ZABBIX_URL")
ZABBIX_API_TOKEN = os.getenv("ZABBIX_API_TOKEN")

# Fail fast if token missing (security)
if not ZABBIX_API_TOKEN:
    raise RuntimeError("ZABBIX_API_TOKEN must be set")

