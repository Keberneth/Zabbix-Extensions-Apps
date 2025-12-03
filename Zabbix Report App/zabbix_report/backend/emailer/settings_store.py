import json
from pathlib import Path
from ..config import DATA_DIR

SETTINGS_FILE = DATA_DIR / "email_settings.json"

DEFAULT_SETTINGS = {
    "smtp_host": "",
    "smtp_port": 587,
    "use_tls": True,
    "username": "",
    "from_addr": "",
}

def get_settings():
    if not SETTINGS_FILE.exists():
        return DEFAULT_SETTINGS
    with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    merged = DEFAULT_SETTINGS.copy()
    merged.update(data)
    return merged

def save_settings(new_settings: dict):
    current = get_settings()
    current.update(new_settings)
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(current, f, indent=2)
