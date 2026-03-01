import json
import threading
import time
from pathlib import Path
from typing import Any, Dict, Tuple

from log import get_logger
from config import DATA_DIR
from settings_store import get_effective_settings
from state import (
    set_cached_map,
    set_netbox_data,
    clear_netbox_data,
    update_cached_map,
    status_started,
    status_finished,
    get_name_to_vm,
)
from zabbix_integration import build_network_map, color_for_node
from netbox_integration import fetch_netbox_vms, fetch_netbox_services
from report_generator import generate_all_reports

logger = get_logger(__name__)

# Manual trigger events
_zabbix_trigger = threading.Event()
_netbox_trigger = threading.Event()
_report_trigger = threading.Event()

_started_lock = threading.Lock()
_started = False


def _netbox_cache_paths() -> Tuple[Path, Path]:
    base = Path(DATA_DIR)
    base.mkdir(parents=True, exist_ok=True)
    return base / "netbox_vms.json", base / "netbox_services.json"


def load_netbox_cache() -> None:
    """Load last NetBox sync from disk into memory.

    This fixes missing env colors after a service restart by ensuring the VM->tags
    mapping exists before the first map build.
    """
    vms_path, svcs_path = _netbox_cache_paths()
    try:
        if vms_path.exists() and svcs_path.exists():
            vms = json.loads(vms_path.read_text(encoding="utf-8"))
            svcs = json.loads(svcs_path.read_text(encoding="utf-8"))
            if isinstance(vms, dict) and isinstance(svcs, list):
                set_netbox_data(vms, svcs)
                logger.info("Loaded NetBox cache from disk (%s, %s)", vms_path, svcs_path)
    except Exception as e:
        logger.warning("Failed to load NetBox cache: %s", e)


def _save_netbox_cache(vms: Dict[str, Any], services: Any) -> None:
    vms_path, svcs_path = _netbox_cache_paths()
    try:
        vms_path.write_text(json.dumps(vms), encoding="utf-8")
        svcs_path.write_text(json.dumps(services), encoding="utf-8")
        try:
            vms_path.chmod(0o600)
            svcs_path.chmod(0o600)
        except Exception:
            pass
    except Exception as e:
        logger.warning("Failed to save NetBox cache: %s", e)


def _recolor_cached_map(enable_netbox: bool) -> None:
    """Update node colors in the current cached map based on current NetBox cache."""
    name_to_vm = get_name_to_vm() if enable_netbox else {}

    def mutator(m: Dict[str, Any]) -> Dict[str, Any]:
        nodes = m.get("nodes") or []
        for node in nodes:
            data = node.get("data") or {}
            node_id = data.get("id") or ""
            ip = data.get("ip") or ""
            data["color"] = color_for_node(node_id, ip, name_to_vm=name_to_vm, enable_netbox=enable_netbox)
            node["data"] = data
        m["nodes"] = nodes
        return m

    update_cached_map(mutator)


def run_zabbix_sync() -> None:
    status_started("zabbix")
    try:
        settings = get_effective_settings()
        new_map = build_network_map(settings)
        set_cached_map(new_map)
        status_finished("zabbix", True)
        logger.info("Zabbix sync completed (nodes=%s, edges=%s)", len(new_map.get("nodes", [])), len(new_map.get("edges", [])))
    except Exception as e:
        status_finished("zabbix", False, str(e))
        logger.exception("Zabbix sync FAILED: %s", e)


def run_netbox_sync() -> None:
    status_started("netbox")
    try:
        settings = get_effective_settings()
        if not settings.enable_netbox:
            clear_netbox_data()
            _recolor_cached_map(enable_netbox=False)
            status_finished("netbox", True)
            logger.info("NetBox integration disabled; cleared cache")
            return

        if not settings.netbox_url or not settings.netbox_token:
            clear_netbox_data()
            _recolor_cached_map(enable_netbox=False)
            status_finished("netbox", False, "NetBox not configured (url/token missing)")
            logger.warning("NetBox not configured; sync skipped")
            return

        vms = fetch_netbox_vms(settings)
        services = fetch_netbox_services(settings)
        set_netbox_data(vms, services)
        _save_netbox_cache(vms, services)

        # Recolor existing map immediately (no need to wait for next Zabbix sync)
        _recolor_cached_map(enable_netbox=True)

        status_finished("netbox", True)
        logger.info("NetBox sync completed (vms=%s, services=%s)", len(vms), len(services))
    except Exception as e:
        status_finished("netbox", False, str(e))
        logger.exception("NetBox sync FAILED: %s", e)


def run_report_generation() -> None:
    status_started("report")
    try:
        generate_all_reports()
        status_finished("report", True)
        logger.info("Report generation completed")
    except Exception as e:
        status_finished("report", False, str(e))
        logger.exception("Report generation FAILED: %s", e)


def zabbix_worker():
    # First run
    run_zabbix_sync()

    while True:
        settings = get_effective_settings()
        # Wait for manual trigger or timeout
        _zabbix_trigger.wait(timeout=settings.zabbix_sync_seconds)
        _zabbix_trigger.clear()
        run_zabbix_sync()


def netbox_worker():
    # First run
    run_netbox_sync()

    while True:
        settings = get_effective_settings()
        _netbox_trigger.wait(timeout=settings.netbox_sync_seconds)
        _netbox_trigger.clear()
        run_netbox_sync()


def report_worker():
    # First run
    run_report_generation()

    while True:
        settings = get_effective_settings()
        _report_trigger.wait(timeout=settings.report_sync_seconds)
        _report_trigger.clear()
        run_report_generation()


def start_workers():
    global _started
    with _started_lock:
        if _started:
            return
        _started = True

    # Load cached NetBox data before any map is built (fixes env colors after restart)
    load_netbox_cache()

    logger.info("Starting background workers (Zabbix, NetBox, Report)")
    threading.Thread(target=zabbix_worker, daemon=True).start()
    threading.Thread(target=netbox_worker, daemon=True).start()
    threading.Thread(target=report_worker, daemon=True).start()


def trigger_zabbix_sync() -> None:
    _zabbix_trigger.set()


def trigger_netbox_sync() -> None:
    _netbox_trigger.set()


def trigger_report_generation() -> None:
    _report_trigger.set()
