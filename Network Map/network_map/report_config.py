import os
import time
import ipaddress
import warnings
import urllib3

from config import NETBOX_TOKEN, REPORT_DIR

# Keep certificate behaviour as before
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

SubjectAltNameWarning = getattr(urllib3.exceptions, "SubjectAltNameWarning", None)
if SubjectAltNameWarning is not None:
    warnings.simplefilter("ignore", SubjectAltNameWarning)

# Output and cache
OUTPUT_DIR = REPORT_DIR
os.makedirs(OUTPUT_DIR, exist_ok=True)

CACHE_DIR = os.path.join(OUTPUT_DIR, "cache")
os.makedirs(CACHE_DIR, exist_ok=True)

# Sliding window config
DAYS = 30
HISTORY_CHUNK = 24 * 3600  # 1 day

def current_time_window():
    """
    Returns (time_from, time_till) for the current 30-day window.
    Computed at call time so a long-running process always has a sliding window.
    """
    now = int(time.time())
    return now - DAYS * 24 * 3600, now


# Hosts to exclude in DrawIO
EXCLUDED_HOSTS = {"Zabbix server"}

# NetBox
NETBOX_HEADERS = {
    "Authorization": f"Token {NETBOX_TOKEN}",
    "Content-Type": "application/json",
    "Accept": "application/json",
}

# Internal IP ranges
INTERNAL_NETWORKS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("172.16.0.0/12"),
]
