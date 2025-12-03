# reports/uptime_trend.py
from __future__ import annotations

import re
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ..cache_store import load_cache, save_cache, touch_cache
from .availability import get_availability  # existing availability logic :contentReference[oaicite:3]{index=3}

CACHE_NAME = "uptime_trend"

def _month_label_from_ts(ts: int) -> str:
    dt = datetime.fromtimestamp(ts, timezone.utc)
    return dt.strftime("%Y-%m")

def _parse_availability_pct(s: str) -> Optional[float]:
    """
    Convert '99.9%' to 99.9 (float). Return None if not parseable.
    """
    if not s or s.lower() == "no data":
        return None
    m = re.match(r"^\s*([0-9]+(?:\.[0-9]+)?)\s*%?\s*$", s)
    if not m:
        return None
    try:
        return float(m.group(1))
    except ValueError:
        return None

def _now_month_labels(months: int) -> List[str]:
    """
    Return list of last `months` months as YYYY-MM, oldest first.
    """
    now = datetime.now(timezone.utc)
    labels: List[str] = []
    year = now.year
    month = now.month
    for _ in range(months):
        labels.append(f"{year:04d}-{month:02d}")
        month -= 1
        if month == 0:
            month = 12
            year -= 1
    labels.reverse()
    return labels

def _load_cache() -> Dict[str, Any]:
    data = load_cache(CACHE_NAME, default={})
    if not isinstance(data, dict):
        data = {}
    data.setdefault("hosts", {})
    return data

def _save_cache(data: Dict[str, Any]) -> None:
    save_cache(CACHE_NAME, data)
    touch_cache(CACHE_NAME)

def refresh_from_recent(days: int = 35, group_ids: Optional[List[str]] = None) -> None:
    """
    Refresh cached monthly uptime using the last `days` of data.

    This should be called whenever someone hits the uptime-trend API
    (or via a cron/scheduled job you may add later).
    """
    rows = get_availability(group_ids=group_ids, days=days)
    if not rows:
        return

    # We use the availability window start to decide which month the
    # computed availability belongs to.
    start_ts = rows[0]["window_start"]
    month_label = _month_label_from_ts(start_ts)

    cache = _load_cache()
    hosts = cache["hosts"]

    for r in rows:
        hostid = r["hostid"]
        host = r.get("host", hostid)
        group_name = ",".join(r.get("group_names", []))
        month_label = _month_label_from_ts(r["window_start"])

        pct = _parse_availability_pct(r.get("availability", ""))
        if pct is None:
            # Don't overwrite existing data for this month on "No data"
            continue

        host_entry = hosts.setdefault(
            hostid,
            {
                "hostid": hostid,
                "host": host,
                "group_name": group_name,
                "months": {},  # month_label -> pct
            },
        )
        host_entry["host"] = host
        host_entry["group_name"] = group_name

        months = host_entry.setdefault("months", {})
        months[month_label] = pct

    _save_cache(cache)

def get_uptime_trend(
    months: int = 12,
    group_filter: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Return last `months` months of uptime per host.

    Structure:
    {
      "month_labels": [...],
      "hosts": [
        {
          "hostid": str,
          "host": str,
          "group_name": str,
          "monthly_uptime": ["99.9", "98.7", "N/A", ...],
        },
        ...
      ]
    }
    """
    months = max(1, min(60, int(months)))
    labels = _now_month_labels(months)

    cache = _load_cache()
    hosts: Dict[str, Any] = cache.get("hosts", {})

    out_hosts: List[Dict[str, Any]] = []

    for hostid, h in hosts.items():
        group_name = h.get("group_name", "")
        if group_filter and group_name not in group_filter:
            continue

        months_map: Dict[str, float] = h.get("months", {})
        row = {
            "hostid": hostid,
            "host": h.get("host", hostid),
            "group_name": group_name,
            "monthly_uptime": [],
        }

        for label in labels:
            val = months_map.get(label)
            if val is None:
                row["monthly_uptime"].append("N/A")
            else:
                row["monthly_uptime"].append(f"{val:.1f}%")

        out_hosts.append(row)

    return {
        "month_labels": labels,
        "hosts": out_hosts,
        "generated_at": int(time.time()),
    }
