from __future__ import annotations

import json
import time
from typing import Dict, Tuple, Set, Any, List, Optional

import requests

from config import ENV_COLOR_MAP
from helpers import classify_env_from_tags, is_public_ip
from settings_store import get_effective_settings, EffectiveSettings
from state import get_name_to_vm, get_netbox_vms
from log import get_logger

logger = get_logger(__name__)


def zabbix_api(method: str, params: Optional[Dict[str, Any]] = None, *, settings: Optional[EffectiveSettings] = None) -> Any:
    settings = settings or get_effective_settings()
    if not settings.zabbix_url or not settings.zabbix_token:
        raise RuntimeError("Zabbix not configured (url/token missing)")

    payload = {
        "jsonrpc": "2.0",
        "method": method,
        "params": params or {},
        "auth": settings.zabbix_token,
        "id": 1,
    }
    resp = requests.post(
        settings.zabbix_url,
        json=payload,
        headers={"Content-Type": "application/json-rpc"},
        verify=False,
        timeout=60,
    )
    resp.raise_for_status()
    data = resp.json()
    if "error" in data:
        raise Exception(data["error"])
    return data["result"]


def get_ip_maps(settings: EffectiveSettings) -> Tuple[Dict[str, str], Dict[str, str]]:
    """Build IP<->host maps.

    ip2host: ip -> host/display
    host2ip: host/display -> first ip

    Uses Zabbix hosts and cached NetBox VMs (if enabled).
    """
    hosts = zabbix_api(
        "host.get",
        {"output": ["host"], "selectInterfaces": ["ip"], "filter": {"status": 0}},
        settings=settings,
    )

    ip2host: Dict[str, str] = {}
    host2ip: Dict[str, str] = {}

    for h in hosts:
        name = h.get("host")
        if not name:
            continue
        for iface in h.get("interfaces", []) or []:
            ip = iface.get("ip")
            if ip:
                ip2host[ip] = name
                host2ip.setdefault(name, ip)

    # Add NetBox VM primary IPs from cache (no live calls here)
    if settings.enable_netbox:
        try:
            for vm in get_netbox_vms().values():
                if not isinstance(vm, dict):
                    continue
                ip4 = vm.get("primary_ip4") and vm["primary_ip4"].get("address")
                if ip4:
                    ip4 = str(ip4).split("/")[0]
                if not ip4:
                    continue
                display = vm.get("display") or vm.get("name")
                if not display:
                    continue
                ip2host[ip4] = display
                host2ip.setdefault(display, ip4)
        except Exception:
            pass

    return ip2host, host2ip


def get_network_items(settings: EffectiveSettings) -> List[Dict[str, Any]]:
    return zabbix_api(
        "item.get",
        {
            "output": ["itemid"],
            "filter": {"name": ["linux-network-connections", "windows-network-connections"]},
            "selectHosts": ["host"],
        },
        settings=settings,
    )


def get_history(itemid: str, time_from: int, time_till: int, settings: EffectiveSettings) -> List[Dict[str, Any]]:
    return zabbix_api(
        "history.get",
        {
            "output": "extend",
            "history": 4,
            "itemids": [itemid],
            "time_from": time_from,
            "time_till": time_till,
            "sortfield": "clock",
            "sortorder": "ASC",
            "limit": 100000,
        },
        settings=settings,
    )


def color_for_node(node_id: str, ip: str, *, name_to_vm: Dict[str, Any], enable_netbox: bool) -> str:
    """Compute node color based on NetBox env tags (if available) + external/public IP."""
    if ip and is_public_ip(ip):
        return ENV_COLOR_MAP["external"]

    if enable_netbox and name_to_vm:
        vm = name_to_vm.get(node_id) or {}
        env = classify_env_from_tags(vm.get("tags") or [])
        return ENV_COLOR_MAP.get(env, ENV_COLOR_MAP["internal-unknown"])

    return ENV_COLOR_MAP["internal-unknown"]


def build_network_map(settings: Optional[EffectiveSettings] = None) -> Dict[str, Any]:
    """Build network map for the last 24 hours."""
    settings = settings or get_effective_settings()

    if not settings.zabbix_url or not settings.zabbix_token:
        logger.warning("Zabbix not configured; returning empty network map")
        return {"nodes": [], "edges": []}

    now = int(time.time())
    tf = now - 24 * 3600
    tt = now

    ip2host, host2ip = get_ip_maps(settings)
    name_to_vm = get_name_to_vm() if settings.enable_netbox else {}

    edges_set: Set[tuple] = set()
    nodes: Set[str] = set()

    for itm in get_network_items(settings):
        itemid = itm.get("itemid")
        if not itemid:
            continue
        try:
            history = get_history(itemid, tf, tt, settings)
        except Exception as e:
            logger.warning("Zabbix history.get failed for item %s: %s", itemid, e)
            continue

        for entry in history:
            try:
                conn = json.loads(entry.get("value") or "")
            except Exception:
                continue
            if not isinstance(conn, dict):
                continue

            incoming = conn.get("incomingconnections", []) or []
            outgoing = conn.get("outgoingconnections", []) or []

            for conn_list, direction in ((incoming, "in"), (outgoing, "out")):
                if isinstance(conn_list, dict):
                    conn_list = [conn_list]
                elif not isinstance(conn_list, list):
                    continue

                for c in conn_list:
                    if not isinstance(c, dict):
                        continue
                    lip = c.get("localip")
                    rip = c.get("remoteip")
                    port = c.get("localport") or c.get("remoteport") or ""

                    if not lip or not rip:
                        continue

                    if direction == "in":
                        src = ip2host.get(rip, rip)
                        dst = ip2host.get(lip, lip)
                    else:
                        src = ip2host.get(lip, lip)
                        dst = ip2host.get(rip, rip)

                    nodes.add(src)
                    nodes.add(dst)

                    is_pub = is_public_ip(rip)
                    edges_set.add((src, dst, port, is_pub))

    # Degrees
    degree: Dict[str, int] = {n: 0 for n in nodes}
    for s, d, _, _ in edges_set:
        degree[s] = degree.get(s, 0) + 1
        degree[d] = degree.get(d, 0) + 1

    # Nodes
    node_data = []
    for n in nodes:
        ip = host2ip.get(n, "")
        label = f"{n} ({ip})" if ip else n

        color = color_for_node(n, ip, name_to_vm=name_to_vm, enable_netbox=settings.enable_netbox)

        node_data.append(
            {
                "data": {
                    "id": n,
                    "label": label,
                    "degree": degree.get(n, 0),
                    "ip": ip,
                    "color": color,
                }
            }
        )

    # Edges
    edge_data = []
    for s, d, p, isp in edges_set:
        edge_data.append(
            {
                "data": {
                    "source": s,
                    "target": d,
                    "label": f"port {p}" if p else "",
                    "isPublic": isp,
                    "srcIp": host2ip.get(s, ""),
                    "dstIp": host2ip.get(d, ""),
                }
            }
        )

    return {"nodes": node_data, "edges": edge_data}
