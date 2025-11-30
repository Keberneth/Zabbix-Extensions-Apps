import os
import ipaddress
import warnings
import urllib3

# --- Zabbix / NetBox configuration (env with fallback) ---

# Docker Desktop: host.docker.internal = Windows host
ZABBIX_URL = os.getenv(
    "ZABBIX_URL",
    "http://host.docker.internal:8080/api_jsonrpc.php",
)
ZABBIX_TOKEN = os.getenv(
    "ZABBIX_TOKEN",
    "5b7ebdb0836be16a97530e521cf0ecf8b6137b209acdd136cf82b7c2c4da7707",
)

NETBOX_URL = os.getenv(
    "NETBOX_URL",
    "http://host.docker.internal:8000",
)
NETBOX_TOKEN = os.getenv(
    "NETBOX_TOKEN",
    "6ab7eccbf5197ce2300f782afe1468f77f69d6ef",
)

ZABBIX_REFRESH_SECONDS = 30 * 60
REPORT_DIR = os.getenv("REPORT_DIR", "/opt/network_map/reports")

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

# Ignore certificate-related warnings (as before)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
SubjectAltNameWarning = getattr(urllib3.exceptions, "SubjectAltNameWarning", None)
if SubjectAltNameWarning is not None:
    warnings.simplefilter("ignore", SubjectAltNameWarning)
