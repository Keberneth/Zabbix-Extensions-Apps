# config.py
from pathlib import Path
import os

APP_ROOT = Path("/opt/zabbix_report").resolve()

DATA_DIR = APP_ROOT / "data"
CACHE_DIR = DATA_DIR / "cache"
TMP_DIR = DATA_DIR / "tmp"
LOG_DIR = DATA_DIR / "logs"  # <--- add this

for d in (DATA_DIR, CACHE_DIR, TMP_DIR, LOG_DIR):
    d.mkdir(parents=True, exist_ok=True)

ZABBIX_URL = os.getenv("ZABBIX_URL", "https://zabbix.skarnes.se/api_jsonrpc.php")
ZABBIX_API_TOKEN = os.getenv("ZABBIX_API_TOKEN", "")
if not ZABBIX_API_TOKEN:
    raise RuntimeError("ZABBIX_API_TOKEN must be set")

# Email settings will be read from a local store (see emailer/settings_store.py)
