# config.py
import os
import ipaddress
import warnings
import urllib3

# -----------------------------------------------------------------------------
# Configuration with hardcoded defaults + environment variable overrides
#
# This keeps the existing import surface used throughout the project
# (e.g. ZABBIX_URL, ZABBIX_TOKEN, NETBOX_URL, NETBOX_TOKEN, REPORT_DIR, etc.).
# -----------------------------------------------------------------------------

def _env(name: str, default: str) -> str:
    """
    Return environment variable value if set and non-empty, otherwise default.
    """
    v = os.getenv(name)
    return v.strip() if v is not None and v.strip() else default


# --- Zabbix / NetBox configuration (defaults hardcoded, can be overridden) ---

# Env var names (so you can standardize deployment):
#   NETWORK_MAP_ZABBIX_URL
#   NETWORK_MAP_ZABBIX_TOKEN
#   NETWORK_MAP_NETBOX_URL
#   NETWORK_MAP_NETBOX_TOKEN
#   NETWORK_MAP_ZABBIX_REFRESH_SECONDS
#   NETWORK_MAP_REPORT_DIR

ZABBIX_URL = _env(
    "NETWORK_MAP_ZABBIX_URL",
    "https://zabbix.example.se/api_jsonrpc.php",
)

ZABBIX_TOKEN = _env(
    "NETWORK_MAP_ZABBIX_TOKEN",
    "this_is_a_fake_token_for_example_purposes",
)

NETBOX_URL = _env(
    "NETWORK_MAP_NETBOX_URL",
    "https://netbox.example.se",
)

NETBOX_TOKEN = _env(
    "NETWORK_MAP_NETBOX_TOKEN",
    "this_is_a_fake_token_for_example_purposes",
)

# Keep numeric config override-friendly
try:
    ZABBIX_REFRESH_SECONDS = int(
        _env("NETWORK_MAP_ZABBIX_REFRESH_SECONDS", str(30 * 60))
    )
except ValueError:
    ZABBIX_REFRESH_SECONDS = 30 * 60

REPORT_DIR = _env("NETWORK_MAP_REPORT_DIR", "/opt/network_map/reports")

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
# Keep ignoring certificate warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# SubjectAltNameWarning exists only in older urllib3; make it optional
SubjectAltNameWarning = getattr(urllib3.exceptions, "SubjectAltNameWarning", None)
if SubjectAltNameWarning is not None:
    warnings.simplefilter("ignore", SubjectAltNameWarning)