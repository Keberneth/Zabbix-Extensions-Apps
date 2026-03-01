import os
import json
from datetime import datetime
from typing import Dict, Any, List, Optional

import requests
import ipaddress

from log import get_logger
from settings_store import get_effective_settings, EffectiveSettings
from report_config import (
    CACHE_DIR,
    INTERNAL_NETWORKS,
    HISTORY_CHUNK,
    CACHE_REFRESH_DAYS,
    current_time_window,
    get_netbox_headers,
)

logger = get_logger(__name__)

_NETBOX_IP_CACHE: Dict[str, Any] = {}


def zabbix_api(method: str, params: Optional[Dict[str, Any]] = None, *, settings: Optional[EffectiveSettings] = None) -> Any:
    settings = settings or get_effective_settings()
    if not settings.zabbix_url or not settings.zabbix_token:
        raise RuntimeError("Zabbix not configured (url/token missing)")

    headers = {"Content-Type": "application/json-rpc"}
    payload = {
        "jsonrpc": "2.0",
        "method": method,
        "params": params or {},
        "auth": settings.zabbix_token,
        "id": 1,
    }
    resp = requests.post(settings.zabbix_url, headers=headers, json=payload, verify=False, timeout=90)
    resp.raise_for_status()
    data = resp.json()
    if "error" in data:
        raise Exception(f"Zabbix API error: {data['error']}")
    return data["result"]


def get_netbox_name_for_ip(ip: str, *, settings: Optional[EffectiveSettings] = None):
    """Resolve an IP to a name using NetBox IPAM.

    Returns None when NetBox is disabled or not configured.
    """
    if not ip:
        return None

    if ip in _NETBOX_IP_CACHE:
        return _NETBOX_IP_CACHE[ip]

    settings = settings or get_effective_settings()
    headers = get_netbox_headers(settings)
    if not headers:
        _NETBOX_IP_CACHE[ip] = None
        return None

    if not settings.netbox_url:
        _NETBOX_IP_CACHE[ip] = None
        return None

    url = f"{settings.netbox_url.rstrip('/')}/api/ipam/ip-addresses/?address={ip}/32"
    resp = requests.get(url, headers=headers, verify=False, timeout=60)
    resp.raise_for_status()
    results = resp.json().get("results", [])
    if not results:
        _NETBOX_IP_CACHE[ip] = None
        return None

    obj = results[0]
    vm = obj.get("assigned_object", {}).get("virtual_machine", {}).get("name")
    if vm:
        _NETBOX_IP_CACHE[ip] = vm
        return vm

    name = obj.get("dns_name")
    _NETBOX_IP_CACHE[ip] = name
    return name


def get_all_hosts_ip_map(*, settings: Optional[EffectiveSettings] = None) -> Dict[str, str]:
    settings = settings or get_effective_settings()
    params = {
        "output": ["hostid", "host"],
        "selectInterfaces": ["ip"],
        "filter": {"status": 0},
    }
    hosts = zabbix_api("host.get", params, settings=settings)
    ip_to_host: Dict[str, str] = {}
    for h in hosts:
        name = h.get("host")
        if not name:
            continue
        for iface in h.get("interfaces", []) or []:
            ip = iface.get("ip")
            if ip:
                ip_to_host[ip] = name

    # resolve IPs where host == IP using NetBox
    for ip, name in list(ip_to_host.items()):
        if name == ip:
            nb = get_netbox_name_for_ip(ip, settings=settings)
            if nb:
                ip_to_host[ip] = nb

    return ip_to_host


def get_network_connection_items(*, settings: Optional[EffectiveSettings] = None) -> List[Dict[str, Any]]:
    settings = settings or get_effective_settings()
    params = {
        "output": ["itemid"],
        "filter": {
            "name": [
                "linux-network-connections",
                "windows-network-connections",
            ]
        },
        "selectHosts": ["host"],
    }
    return zabbix_api("item.get", params, settings=settings)


def _history_cache_file(itemid: str, chunk_start: int) -> str:
    return os.path.join(CACHE_DIR, f"history_{itemid}_{chunk_start}.json")


def cleanup_history_cache() -> None:
    """Remove cached chunks that are completely older than the current 30-day window."""
    time_from, _ = current_time_window()
    min_keep_start = (time_from // HISTORY_CHUNK) * HISTORY_CHUNK
    for fname in os.listdir(CACHE_DIR):
        if not fname.startswith("history_") or not fname.endswith(".json"):
            continue
        base = fname[:-5]
        parts = base.split("_")
        if len(parts) < 3:
            continue
        try:
            chunk_start = int(parts[-1])
        except ValueError:
            continue
        if chunk_start + HISTORY_CHUNK < min_keep_start:
            try:
                os.remove(os.path.join(CACHE_DIR, fname))
            except OSError:
                pass


def get_connection_history(itemid: str, *, settings: Optional[EffectiveSettings] = None) -> List[Dict[str, Any]]:
    """Fetch history for given itemid for the last 30 days using local cache."""
    settings = settings or get_effective_settings()

    all_entries: List[Dict[str, Any]] = []

    time_from, time_till = current_time_window()
    first_chunk_start = (time_from // HISTORY_CHUNK) * HISTORY_CHUNK
    last_chunk_start = (time_till // HISTORY_CHUNK) * HISTORY_CHUNK

    refresh_cutoff = time_till - (CACHE_REFRESH_DAYS * HISTORY_CHUNK)

    for chunk_start in range(first_chunk_start, last_chunk_start + 1, HISTORY_CHUNK):
        chunk_end = chunk_start + HISTORY_CHUNK
        cache_file = _history_cache_file(itemid, chunk_start)

        # Decide whether we can trust the cache for this chunk.
        must_refresh = False

        # Always refresh current/ongoing chunk.
        if chunk_end > time_till:
            must_refresh = True

        # Refresh the most recent N days each run.
        if chunk_start >= refresh_cutoff:
            must_refresh = True

        # If a cache file exists but was written before the chunk ended, it is
        # likely partial (created while the day was still in progress).
        if not must_refresh and os.path.exists(cache_file):
            try:
                mtime = int(os.path.getmtime(cache_file))
                if mtime < chunk_end:
                    must_refresh = True
            except OSError:
                must_refresh = True

        # Use cache when allowed.
        if not must_refresh and os.path.exists(cache_file):
            try:
                with open(cache_file, "r", encoding="utf-8") as f:
                    chunk = json.load(f)
                if isinstance(chunk, list):
                    all_entries.extend(chunk)
                    continue
            except Exception as e:
                logger.warning("Report cache read failed for %s: %s", cache_file, e)
                must_refresh = True

        # Fetch fresh chunk from Zabbix (and update cache).
        req_end = min(chunk_end, time_till)
        params = {
            "output": "extend",
            "history": 4,
            "itemids": [itemid],
            "time_from": chunk_start,
            "time_till": req_end,
            "sortfield": "clock",
            "sortorder": "ASC",
            "limit": 100000,
        }
        try:
            chunk = zabbix_api("history.get", params, settings=settings)
        except Exception as e:
            logger.warning(
                "[REPORT] history.get failed for item %s %s-%s: %s",
                itemid,
                chunk_start,
                req_end,
                e,
            )
            continue

        if isinstance(chunk, list):
            all_entries.extend(chunk)

        try:
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(chunk, f)
        except Exception as e:
            logger.warning("[REPORT] Failed to write cache %s: %s", cache_file, e)

    return all_entries


def parse_history_connections(items, ip_to_host, *, settings: Optional[EffectiveSettings] = None):
    settings = settings or get_effective_settings()
    time_from, time_till = current_time_window()
    agg: Dict[Any, Dict[str, Any]] = {}
    for itm in items:
        host = itm.get("hosts", [{}])[0].get("host", "")
        itemid = itm.get("itemid")
        if not itemid:
            continue
        history = get_connection_history(itemid, settings=settings)
        for entry in history:
            timestamp = int(entry.get("clock", 0))
            if timestamp < time_from or timestamp > time_till:
                continue

            raw = entry.get("value") or ""
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                continue

            inc = data.get("incomingconnections", []) or []
            out = data.get("outgoingconnections", []) or []
            if isinstance(inc, dict):
                inc = [inc]
            if isinstance(out, dict):
                out = [out]

            for conn_list, ctype in ((inc, "incoming"), (out, "outgoing")):
                for c in conn_list:
                    if not isinstance(c, dict):
                        continue
                    rip = c.get("remoteip", "")
                    local_ip = c.get("localip", "")
                    port = c.get("localport" if ctype == "incoming" else "remoteport", "")
                    remote_host = ip_to_host.get(rip, rip)

                    key = (ctype, host, local_ip, remote_host, rip, port)
                    if key not in agg:
                        agg[key] = {"count": 0, "latest_ts": 0}
                    agg[key]["count"] += 1
                    if timestamp > agg[key]["latest_ts"]:
                        agg[key]["latest_ts"] = timestamp

    rows = []
    for (ctype, local_host, local_ip, remote_host, remote_ip, port), v in agg.items():
        rows.append(
            {
                "type": ctype,
                "local_host": local_host,
                "local_ip": local_ip,
                "remote_host": remote_host,
                "remote_ip": remote_ip,
                "port": port,
                "count": v["count"],
                "timestamp": datetime.utcfromtimestamp(v["latest_ts"]).isoformat() + "Z",
            }
        )
    return rows


def filter_internal(rows):
    filtered = []
    for r in rows:
        try:
            lip = ipaddress.ip_address(r["local_ip"])
            rip = ipaddress.ip_address(r["remote_ip"])
        except ValueError:
            continue
        if any(lip in net for net in INTERNAL_NETWORKS) and any(rip in net for net in INTERNAL_NETWORKS):
            filtered.append(r)
    return filtered


def filter_public(rows):
    filtered = []
    for r in rows:
        try:
            lip = ipaddress.ip_address(r["local_ip"])
            rip = ipaddress.ip_address(r["remote_ip"])
        except ValueError:
            continue
        if lip.is_loopback or rip.is_loopback:
            continue
        if not any(rip in net for net in INTERNAL_NETWORKS):
            filtered.append(r)
    return filtered
