import threading
import time
from typing import Dict, List, Any, Optional

# Network map cache
_cached_map: Dict[str, Any] = {"nodes": [], "edges": []}
_last_updated: int = 0

# NetBox cache
_netbox_vms: Dict[str, Any] = {}
_netbox_services: List[Dict[str, Any]] = []
_name_to_vm: Dict[str, Any] = {}

# Sync/report status
_status_lock = threading.Lock()
_status: Dict[str, Dict[str, Any]] = {
    "zabbix": {"running": False, "last_run": None, "last_ok": None, "last_error": None},
    "netbox": {"running": False, "last_run": None, "last_ok": None, "last_error": None},
    "report": {"running": False, "last_run": None, "last_ok": None, "last_error": None},
}

# Locks
_cached_map_lock = threading.Lock()
_netbox_lock = threading.Lock()


# --- Network map ---

def set_cached_map(new_map: Dict[str, Any]) -> None:
    global _cached_map, _last_updated
    with _cached_map_lock:
        _cached_map = new_map
        _last_updated = int(time.time())


def update_cached_map(mutator_fn) -> None:
    """Apply a mutation function to the cached map under lock."""
    global _cached_map, _last_updated
    with _cached_map_lock:
        _cached_map = mutator_fn(_cached_map) or _cached_map
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


def clear_netbox_data() -> None:
    set_netbox_data({}, [])


def get_netbox_vms() -> Dict[str, Any]:
    with _netbox_lock:
        return _netbox_vms


def get_netbox_services() -> List[Dict[str, Any]]:
    with _netbox_lock:
        return _netbox_services


def get_name_to_vm() -> Dict[str, Any]:
    with _netbox_lock:
        return _name_to_vm


# --- Status ---

def status_started(component: str) -> None:
    now = int(time.time())
    with _status_lock:
        if component not in _status:
            _status[component] = {"running": False, "last_run": None, "last_ok": None, "last_error": None}
        _status[component]["running"] = True
        _status[component]["last_run"] = now
        _status[component]["last_error"] = None


def status_finished(component: str, ok: bool, error: Optional[str] = None) -> None:
    with _status_lock:
        if component not in _status:
            _status[component] = {"running": False, "last_run": None, "last_ok": None, "last_error": None}
        _status[component]["running"] = False
        _status[component]["last_ok"] = bool(ok)
        _status[component]["last_error"] = error


def get_status() -> Dict[str, Any]:
    with _status_lock:
        return {k: dict(v) for k, v in _status.items()}
