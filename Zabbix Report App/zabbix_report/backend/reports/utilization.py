import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from ..zabbix_client import call as zbx_call


TARGET_SUBSTRINGS = [
    "utilization (cpu)",
    "utilization (ram)",
]


def _name_matches(item_name: str) -> bool:
    lname = item_name.lower()
    return any(substr in lname for substr in TARGET_SUBSTRINGS)


def _is_cpu_item(name: str) -> bool:
    return "cpu" in name.lower()


def _get_all_hosts() -> List[Dict[str, Any]]:
    return zbx_call(
        "host.get",
        {
            "output": ["hostid", "host", "name"],
            "filter": {"status": 0},
        },
    )


def _get_items_for_host(hostid: str) -> List[Dict[str, Any]]:
    return zbx_call(
        "item.get",
        {
            "hostids": hostid,
            "output": ["itemid", "name", "value_type"],
            "filter": {"status": 0},
        },
    )


def _get_history(
    itemid: str,
    value_type: int,
    time_from: int,
    time_till: int,
    limit: int = 100000,
) -> List[Dict[str, Any]]:
    rows = zbx_call(
        "history.get",
        {
            "output": "extend",
            "history": value_type,
            "itemids": itemid,
            "time_from": time_from,
            "time_till": time_till,
            "sortfield": "clock",
            "sortorder": "ASC",
            "limit": limit,
        },
    )
    out: List[Dict[str, Any]] = []
    for r in rows:
        try:
            value = float(r["value"])
        except Exception:
            continue
        out.append(
            {
                "clock": int(r["clock"]),
                "value": value,
            }
        )
    return out


def _unix_to_datetime(ts: int) -> datetime:
    return datetime.utcfromtimestamp(int(ts))


def get_service_utilization(
    host_ids: Optional[List[str]] = None,
    days: int = 30,
) -> Dict[str, Any]:
    """
    Return process/service utilization (CPU/RAM) per host, based on the original
    service_utilization_report.py but without generating PDFs. 

    Result:
    {
      "time_from": int,
      "time_till": int,
      "hosts": [
        {
          "hostid": str,
          "host": str,
          "items": [
            {
              "itemid": str,
              "name": str,
              "metric": "cpu" or "ram",
              "points": [{"clock": int, "value": float}, ...]
            },
            ...
          ]
        },
        ...
      ]
    }
    """
    days = max(1, days)
    time_now = int(time.time())
    time_from = time_now - days * 24 * 3600
    time_till = time_now

    if host_ids is None:
        hosts = _get_all_hosts()
    else:
        hosts = zbx_call(
            "host.get",
            {
                "output": ["hostid", "host", "name"],
                "hostids": host_ids,
            },
        )

    result_hosts: List[Dict[str, Any]] = []

    for host in hosts:
        hostid = host["hostid"]
        hostname = host.get("name") or host.get("host", hostid)

        items = _get_items_for_host(hostid)
        filtered = [
            it
            for it in items
            if _name_matches(it["name"]) and int(it["value_type"]) in (0, 3)
        ]
        if not filtered:
            continue

        host_items: List[Dict[str, Any]] = []

        for it in filtered:
            itemid = it["itemid"]
            name = it["name"]
            value_type = int(it["value_type"])

            history = _get_history(itemid, value_type, time_from, time_till)
            if not history:
                continue

            if _is_cpu_item(name):
                metric = "cpu"
                # values are already percent
                points = history
            else:
                metric = "ram"
                # convert bytes -> MB
                points = [
                    {
                        "clock": h["clock"],
                        "value": h["value"] / (1024 ** 2),
                    }
                    for h in history
                ]

            host_items.append(
                {
                    "itemid": itemid,
                    "name": name,
                    "metric": metric,
                    "points": points,
                }
            )

        if host_items:
            result_hosts.append(
                {
                    "hostid": hostid,
                    "host": hostname,
                    "items": host_items,
                }
            )

    return {
        "time_from": time_from,
        "time_till": time_till,
        "hosts": result_hosts,
    }
