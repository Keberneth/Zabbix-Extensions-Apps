import json
import time
from typing import Dict, Tuple, Set, Any, List, Optional

import requests

from config import ZABBIX_URL, ZABBIX_TOKEN, ENV_COLOR_MAP
from helpers import classify_env, is_public_ip
from netbox_integration import fetch_netbox_vms
from state import get_name_to_vm
from log import get_logger

logger = get_logger(__name__)

def zabbix_api(method: str, params: Optional[Dict[str, Any]] = None) -> Any:
    payload = {
        "jsonrpc": "2.0",
        "method": method,
        "params": params or {},
        "auth": ZABBIX_TOKEN,
        "id": 1,
    }
    resp = requests.post(
        ZABBIX_URL,
        json=payload,
        headers={"Content-Type": "application/json-rpc"},
        verify=False,
    )
    resp.raise_for_status()
    data = resp.json()
    if "error" in data:
        raise Exception(data["error"])
    return data["result"]


def get_ip_maps() -> Tuple[Dict[str, str], Dict[str, str]]:
    """
    Returns:
        ip2host: ip -> host/display
        host2ip: host/display -> first ip
    Uses Zabbix hosts and NetBox VMs (as in original code).
    """
    hosts = zabbix_api(
        "host.get",
        {"output": ["host"], "selectInterfaces": ["ip"], "filter": {"status": 0}},
    )
    ip2host: Dict[str, str] = {}
    host2ip: Dict[str, str] = {}

    for h in hosts:
        name = h["host"]
        for iface in h.get("interfaces", []):
            ip = iface.get("ip")
            if ip:
                ip2host[ip] = name
                host2ip.setdefault(name, ip)

    # add NetBox VM primary IPs like original
    try:
        for vm in fetch_netbox_vms().values():
            ip4 = vm.get("primary_ip4") and vm["primary_ip4"]["address"].split("/")[0]
            if ip4:
                display = vm.get("display") or vm.get("name")
                ip2host[ip4] = display
                host2ip.setdefault(display, ip4)
    except Exception:
        pass

    return ip2host, host2ip


def get_network_items() -> List[Dict[str, Any]]:
    return zabbix_api(
        "item.get",
        {
            "output": ["itemid"],
            "filter": {
                "name": [
                    "linux-network-connections",
                    "windows-network-connections",
                ]
            },
            "selectHosts": ["host"],
        },
    )


def get_history(itemid: str, time_from: int, time_till: int) -> List[Dict[str, Any]]:
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
            "limit": 100000,  # keep full 24h window
        },
    )


def build_network_map() -> Dict[str, Any]:
    """
    Build network map for the last 24 hours (24h window retained).
    """
    now = int(time.time())
    tf = now - 24 * 3600
    tt = now

    ip2host, host2ip = get_ip_maps()
    name_to_vm = get_name_to_vm()

    edges_set: Set[tuple] = set()
    nodes: Set[str] = set()

    for itm in get_network_items():
        itemid = itm["itemid"]
        history = get_history(itemid, tf, tt)
        for entry in history:
            try:
                conn = json.loads(entry["value"])
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

        vm = name_to_vm.get(n) or {}
        tags = vm.get("tags") or []
        tag_names = []
        for t in tags:
            if isinstance(t, dict):
                tag_names.append(t.get("name") or t.get("slug") or "")
            elif isinstance(t, str):
                tag_names.append(t)
        # remove empties
        tag_names = [x for x in tag_names if x]

        env = classify_env(tag_names)

        color = (
            ENV_COLOR_MAP["external"]
            if is_public_ip(ip)
            else ENV_COLOR_MAP.get(env, ENV_COLOR_MAP["internal-unknown"])
        )

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
