import time
from datetime import datetime
import re
from typing import Any, Dict, List

from ..zabbix_client import call as zbx_call


TARGET_NAME = "Interface [a()]: Bits sent"
OPTIONAL_KEY = ""  # keep empty to only check name, as original script 


def _sanitize(x: str) -> str:
    return re.sub(r"[^\w\-. ]+", "_", (x or "").strip())[:200] or "val"


def _get_monitored_hosts() -> List[Dict[str, Any]]:
    return zbx_call(
        "host.get",
        {
            "output": ["hostid", "host", "name"],
            "filter": {"status": 0},
        },
    )


def _get_host_items(hostid: str) -> List[Dict[str, Any]]:
    return zbx_call(
        "item.get",
        {
            "hostids": [hostid],
            "output": ["itemid", "name", "key_", "value_type", "units", "delay"],
            "filter": {"status": 0},
        },
    )


def _history(
    itemid: str,
    value_type: int,
    time_from: int,
    time_till: int,
    chunk: int,
    max_per_call: int = 10000,
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for start in range(time_from, time_till, chunk):
        end = min(start + chunk, time_till)
        part = zbx_call(
            "history.get",
            {
                "output": "extend",
                "history": int(value_type),
                "itemids": [itemid],
                "time_from": start,
                "time_till": end,
                "sortfield": "clock",
                "sortorder": "ASC",
                "limit": max_per_call,
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


def _trends(itemid: str, time_from: int, time_till: int) -> List[Dict[str, Any]]:
    rows = zbx_call(
        "trend.get",
        {
            "output": ["clock", "num", "value_min", "value_avg", "value_max"],
            "itemids": [itemid],
            "time_from": time_from,
            "time_till": time_till,
            "sortfield": "clock",
            "sortorder": "ASC",
        },
    )
    out: List[Dict[str, Any]] = []
    for r in rows:
        try:
            v = float(r["value_avg"])
        except Exception:
            continue
        out.append(
            {
                "clock": int(r["clock"]),
                "ns": 0,
                "value": v,
            }
        )
    return out


def get_firewall_interface_usage(
    days: int = 30,
    chunk_seconds: int = 6 * 3600,
) -> List[Dict[str, Any]]:
    """
    Export 30-day history for "Interface [a()]: Bits sent" items on all monitored
    hosts, based on firewall_interface_usage.py but returned as a list of
    documents instead of JSON files. 

    Each document:
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
    days = max(1, days)
    time_till = int(time.time())
    time_from = time_till - days * 24 * 3600

    hosts = _get_monitored_hosts()
    docs: List[Dict[str, Any]] = []

    for h in hosts:
        hid = h["hostid"]
        hname = h.get("name") or h.get("host") or hid

        items = _get_host_items(hid)
        it = next(
            (
                x
                for x in items
                if x.get("name") == TARGET_NAME
                and (not OPTIONAL_KEY or x.get("key_") == OPTIONAL_KEY)
            ),
            None,
        )
        if not it:
            continue

        vt = int(it.get("value_type", 3))
        series = _history(it["itemid"], vt, time_from, time_till, chunk_seconds)
        used_trends = False
        if not series:
            series = _trends(it["itemid"], time_from, time_till)
            used_trends = bool(series)

        doc = {
            "hostid": hid,
            "host": h.get("host", ""),
            "name": h.get("name", ""),
            "exported_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
            "window": {"from": time_from, "till": time_till, "days": days},
            "item": {
                "itemid": it["itemid"],
                "name": it.get("name", ""),
                "key_": it.get("key_", ""),
                "value_type": vt,
                "units": it.get("units", ""),
                "delay": it.get("delay", ""),
                "source": "history.get" if not used_trends else "trend.get(avg)",
            },
            "history": [
                {
                    "clock": int(r["clock"]),
                    "ns": int(r.get("ns", 0)),
                    "value": r["value"],
                }
                for r in series
            ],
            "file_suffix": f"{_sanitize(hname)}-fgate.netif.out[a]",
        }

        docs.append(doc)

    return docs
