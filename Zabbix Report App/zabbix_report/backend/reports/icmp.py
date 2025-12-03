import re
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from ..zabbix_client import call as zbx_call


KEY_RX = re.compile(r"^(icmpping|icmppingsec|icmppingloss)(\[.*\])?$")
NAME_BY_KEY = {
    "icmpping": "ICMP",
    "icmppingsec": "ICMP-response-time",
    "icmppingloss": "ICMP-loss",
}


def _sanitize(name: str) -> str:
    return re.sub(r"[^\w\-. ]+", "_", (name or "").strip())[:200] or "val"


def _get_group_ids(group_names: List[str]) -> List[str]:
    if not group_names:
        return []
    res = zbx_call(
        "hostgroup.get",
        {
            "output": ["groupid", "name"],
            "filter": {"name": group_names},
        },
    )
    return [g["groupid"] for g in res]


def _get_hosts(group_ids: List[str]) -> List[Dict[str, Any]]:
    return zbx_call(
        "host.get",
        {
            "output": ["hostid", "host", "name"],
            "groupids": group_ids,
            "filter": {"status": 0},  # monitored only
        },
    )


def _get_items(hostids: List[str]) -> List[Dict[str, Any]]:
    res = zbx_call(
        "item.get",
        {
            "output": ["itemid", "hostid", "key_", "name", "value_type"],
            "hostids": hostids,
            "filter": {"status": 0},
            "templated": False,
            "selectHosts": ["host", "name"],
        },
    )
    return [it for it in res if KEY_RX.match(it.get("key_", ""))]


def _history(itemid: str, value_type: int, time_from: int, time_till: int, chunk: int) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for start in range(time_from, time_till, chunk):
        end = min(start + chunk, time_till)
        part = zbx_call(
            "history.get",
            {
                "output": "extend",
                "history": value_type,  # 0=float, 3=unsigned
                "itemids": itemid,
                "time_from": start,
                "time_till": end,
                "sortfield": "clock",
                "sortorder": "ASC",
            },
        )
        if part:
            rows.extend(part)
    if int(value_type) in (0, 3):
        for r in rows:
            try:
                r["value"] = float(r["value"])
            except Exception:
                pass
    return rows


def _item_suffix_from_key(key: str) -> str:
    m = KEY_RX.match(key or "")
    if not m:
        return _sanitize(key)
    base = m.group(1)
    return NAME_BY_KEY.get(base, _sanitize(base))


def get_icmp_history(
    group_names: Optional[List[str]] = None,
    days: int = 30,
    history_chunk_seconds: int = 24 * 3600,
) -> List[Dict[str, Any]]:
    """
    Export ICMP history per item, similar to icmp_avalibility.py, but as a list
    of documents instead of files. 

    Each element:
    {
      "hostid": str,
      "host": str,
      "name": str,
      "exported_at": ISO8601,
      "window": {"from": int, "till": int, "days": int},
      "item": {...},
      "history": [{"clock": int, "ns": int, "value": float}, ...],
    }
    """
    if not group_names:
        group_names = ["Network/Firewall", "Network/Switch"]

    days = max(1, days)
    time_till = int(time.time())
    time_from = time_till - days * 24 * 3600

    group_ids = _get_group_ids(group_names)
    hosts = _get_hosts(group_ids)
    if not hosts:
        return []

    host_index = {
        h["hostid"]: {
            "host": h.get("host", ""),
            "name": h.get("name") or h.get("host", ""),
        }
        for h in hosts
    }
    hostids = list(host_index.keys())

    items = _get_items(hostids)
    if not items:
        return []

    docs: List[Dict[str, Any]] = []

    for it in items:
        hid = it["hostid"]
        meta = host_index.get(hid, {})
        host_name = meta.get("name") or meta.get("host") or hid
        vt = int(it.get("value_type", 0))
        hist = _history(it["itemid"], vt, time_from, time_till, history_chunk_seconds)

        doc = {
            "hostid": hid,
            "host": meta.get("host", ""),
            "name": host_name,
            "exported_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
            "window": {"from": time_from, "till": time_till, "days": days},
            "item": {
                "itemid": it["itemid"],
                "name": it.get("name", ""),
                "key_": it.get("key_", ""),
                "value_type": vt,
            },
            "history": [
                {
                    "clock": int(h["clock"]),
                    "ns": int(h.get("ns", 0)),
                    "value": h["value"],
                }
                for h in hist
            ],
            "file_suffix": _item_suffix_from_key(it.get("key_", "")),
        }
        docs.append(doc)

    return docs
