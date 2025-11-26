from typing import Dict, List, Any

import requests

from config import NETBOX_URL, NETBOX_TOKEN


def fetch_netbox_vms() -> Dict[str, Any]:
    vms: Dict[str, Any] = {}
    url = f"{NETBOX_URL}/api/virtualization/virtual-machines/"
    headers = {"Authorization": f"Token {NETBOX_TOKEN}"}
    params = {"limit": 1000}
    while url:
        r = requests.get(url, headers=headers, params=params, verify=False)
        r.raise_for_status()
        js = r.json()
        for vm in js.get("results", []):
            vms[str(vm["id"])] = vm
        url = js.get("next")
        params = None
    return vms


def fetch_netbox_services() -> List[Dict[str, Any]]:
    svcs: List[Dict[str, Any]] = []
    url = f"{NETBOX_URL}/api/ipam/services/"
    headers = {"Authorization": f"Token {NETBOX_TOKEN}"}
    params = {"limit": 1000}
    while url:
        r = requests.get(url, headers=headers, params=params, verify=False)
        r.raise_for_status()
        js = r.json()
        svcs.extend(js.get("results", []))
        url = js.get("next")
        params = None
    return svcs
