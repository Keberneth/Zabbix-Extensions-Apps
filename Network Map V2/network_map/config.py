import ipaddress
import warnings
import urllib3

# --- Zabbix / NetBox configuration (kept hardcoded) ---

ZABBIX_URL             = "https://zabbix.example.se/api_jsonrpc.php"
ZABBIX_TOKEN           = "this_is_a_fake_token_for_example_purposes"
NETBOX_URL             = "https://netbox.example.se"
NETBOX_TOKEN           = "this_is_a_fake_token_for_example_purposes"
ZABBIX_REFRESH_SECONDS = 30 * 60
REPORT_DIR             = "/opt/network_map/reports"

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