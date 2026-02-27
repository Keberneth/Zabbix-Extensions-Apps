import threading
import time
from typing import Dict, List, Any

# Network map cache
_cached_map: Dict[str, Any] = {"nodes": [], "edges": []}
_last_updated: int = 0

# NetBox cache
_netbox_vms: Dict[str, Any] = {}
_netbox_services: List[Dict[str, Any]] = []
_name_to_vm: Dict[str, Any] = {}

# Locks
_cached_map_lock = threading.Lock()
_netbox_lock = threading.Lock()


# --- Network map ---

def set_cached_map(new_map: Dict[str, Any]) -> None:
    global _cached_map, _last_updated
    with _cached_map_lock:
        _cached_map = new_map
        _last_updated = int(time.time())


def get_cached_map() -> Dict[str, Any]:
    with _cached_map_lock:
        return _cached_map


def get_last_updated() -> int:
    with _cached_map_lock:
        return _last_updated


# --- NetBox data ---

def set_netbox_data(vms: Dict[str, Any], services: List[Dict[str, Any]]) -> None:
    global _netbox_vms, _netbox_services, _name_to_vm
    with _netbox_lock:
        _netbox_vms = dict(vms)
        _netbox_services = list(services)
        _name_to_vm = {}
        for vm in _netbox_vms.values():
            if not isinstance(vm, dict):
                continue
            if vm.get("name"):
                _name_to_vm[vm["name"]] = vm
            if vm.get("display"):
                _name_to_vm[vm["display"]] = vm

def get_netbox_vms() -> Dict[str, Any]:
    with _netbox_lock:
        return _netbox_vms


def get_netbox_services() -> List[Dict[str, Any]]:
    with _netbox_lock:
        return _netbox_services


def get_name_to_vm() -> Dict[str, Any]:
    with _netbox_lock:
        return _name_to_vm
