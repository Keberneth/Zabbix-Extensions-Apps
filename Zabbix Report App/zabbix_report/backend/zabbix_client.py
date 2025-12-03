import requests
from typing import Any, Dict
from .config import ZABBIX_URL, ZABBIX_API_TOKEN

session = requests.Session()
session.headers.update({"Content-Type": "application/json-rpc"})

def call(method: str, params: Dict[str, Any]) -> Any:
    payload = {
        "jsonrpc": "2.0",
        "method": method,
        "params": params,
        "auth": ZABBIX_API_TOKEN,
        "id": 1,
    }
    r = session.post(ZABBIX_URL, json=payload, timeout=(10, 60), verify=True)
    r.raise_for_status()
    data = r.json()
    if "error" in data:
        e = data["error"]
        raise RuntimeError(f"Zabbix API error {e.get('code')}: {e.get('message')} - {e.get('data')}")
    return data["result"]
