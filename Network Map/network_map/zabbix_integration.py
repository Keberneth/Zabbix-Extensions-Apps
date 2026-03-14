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



def _collect_env_from_tags(vm: Dict[str, Any]) -> str:
    tags = vm.get("tags") or []
    candidates: Set[str] = set()

    if isinstance(tags, list):
        for tag in tags:
            if isinstance(tag, dict):
                tag_val = tag.get("slug") or tag.get("name") or tag.get("display") or ""
            else:
                tag_val = str(tag)

            env_guess = classify_env(tag_val)
            if env_guess != "unknown":
                candidates.add(env_guess)

    for pref in ("prod", "qa", "test", "dev"):
        if pref in candidates:
            return pref
    return "unknown"



def build_network_map() -> Dict[str, Any]:
    """
    Build network map for the last 24 hours (24h window retained).
    """
    now = int(time.time())
    tf = now - 24 * 3600
    tt = now

    ip2host, host2ip = get_ip_maps()
    node_ip_map: Dict[str, str] = dict(host2ip)
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

                    local_ip = c.get("localip")
                    remote_ip = c.get("remoteip")
                    local_port = str(c.get("localport") or "")
                    remote_port = str(c.get("remoteport") or "")

                    if not local_ip or not remote_ip:
                        continue

                    if direction == "in":
                        src = ip2host.get(remote_ip, remote_ip)
                        dst = ip2host.get(local_ip, local_ip)
                        src_ip = remote_ip
                        dst_ip = local_ip
                        service_port = local_port
                    else:
                        src = ip2host.get(local_ip, local_ip)
                        dst = ip2host.get(remote_ip, remote_ip)
                        src_ip = local_ip
                        dst_ip = remote_ip
                        service_port = remote_port

                    nodes.add(src)
                    nodes.add(dst)
                    node_ip_map.setdefault(src, src_ip)
                    node_ip_map.setdefault(dst, dst_ip)

                    is_public = is_public_ip(remote_ip)
                    edges_set.add(
                        (
                            src,
                            dst,
                            service_port,
                            local_port,
                            remote_port,
                            is_public,
                            src_ip,
                            dst_ip,
                        )
                    )

    # Degrees
    degree: Dict[str, int] = {n: 0 for n in nodes}
    for src, dst, *_ in edges_set:
        degree[src] = degree.get(src, 0) + 1
        degree[dst] = degree.get(dst, 0) + 1

    # Nodes
    node_data = []
    for node_name in nodes:
        ip = node_ip_map.get(node_name, "")
        label = f"{node_name} ({ip})" if ip and ip != node_name else node_name

        vm = name_to_vm.get(node_name) or {}
        env = _collect_env_from_tags(vm)

        if is_public_ip(ip):
            color = ENV_COLOR_MAP["external"]
        elif env != "unknown":
            color = ENV_COLOR_MAP.get(env, ENV_COLOR_MAP["internal-unknown"])
        else:
            color = ENV_COLOR_MAP["internal-unknown"]

        node_data.append(
            {
                "data": {
                    "id": node_name,
                    "label": label,
                    "degree": degree.get(node_name, 0),
                    "ip": ip,
                    "color": color,
                }
            }
        )

    # Edges
    edge_data = []
    for src, dst, service_port, local_port, remote_port, is_public, src_ip, dst_ip in edges_set:
        edge_data.append(
            {
                "data": {
                    "source": src,
                    "target": dst,
                    "label": f"port {service_port}" if service_port else "",
                    "servicePort": service_port,
                    "localPort": local_port,
                    "remotePort": remote_port,
                    "isPublic": is_public,
                    "srcIp": src_ip,
                    "dstIp": dst_ip,
                }
            }
        )

    return {"nodes": node_data, "edges": edge_data}
