from __future__ import annotations

import time
import calendar
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from ..zabbix_client import call as zbx_call
from ..cache_store import load_cache, save_cache, touch_cache


CACHE_NAME = "incident_trends"
SEVERITY_MAP = {
    "2": "Warning",
    "3": "Average",
    "4": "High",
    "5": "Critical",
}


def _month_label(ts: int) -> str:
    dt = datetime.fromtimestamp(ts, timezone.utc)
    return dt.strftime("%Y-%m")


def _now_month_labels(months: int) -> List[str]:
    now = datetime.now(timezone.utc)
    labels = []
    year, month = now.year, now.month
    for _ in range(months):
        labels.append(f"{year:04d}-{month:02d}")
        month -= 1
        if month == 0:
            month = 12
            year -= 1
    labels.reverse()
    return labels


def refresh_incident_cache(months: int = 2) -> None:
    """
    Refresh incident cache by querying Zabbix events for triggers
    for the last `months` months.
    """

    now = datetime.now(timezone.utc)
    # Start from the 1st day 00:00 of the oldest month
    oldest = _now_month_labels(months)[0]
    oldest_year, oldest_month = map(int, oldest.split("-"))
    start = datetime(oldest_year, oldest_month, 1, tzinfo=timezone.utc).timestamp()

    events = zbx_call("event.get", {
        "output": ["eventid", "clock", "objectid"],
        "selectHosts": ["hostid", "name"],
        "selectTags": "extend",
        "source": 0,      # trigger events
        "object": 0,      # trigger object
        # Only PROBLEM events, Warning/Average/High/Critical
        "value": 1,
        "severities": [2, 3, 4, 5],
        "time_from": int(start),
        "time_till": int(now.timestamp()),
    })

    # Build month aggregation
    cache = {
        "months": {},              # month -> list of events
        "top_triggers": {},        # triggerid -> total count
        "per_host": {},            # hostid -> {month: count}
        "severity": {},            # severity -> {month: count}
        "investigate": [],         # list of triggers needing investigation
        "generated_at": int(time.time()),
    }

    # Initialize month buckets
    month_labels = _now_month_labels(months)
    for m in month_labels:
        cache["months"][m] = []

    # For 30-day investigation check
    thirty_days_ago = int(time.time()) - 30 * 86400
    trigger_counter_30d: Dict[str, int] = {}

    # Process events
    for ev in events:
        ts = int(ev["clock"])
        month = _month_label(ts)

        if month not in cache["months"]:
            continue

        trigger_id = ev["objectid"]
        hosts = ev.get("hosts", [])
        hostid = hosts[0]["hostid"] if hosts else "unknown"
        hostname = hosts[0].get("name") if hosts else "unknown"

        # We need severity → requires trigger.get
        trig = zbx_call("trigger.get", {
            "output": ["triggerid", "priority", "description"],
            "triggerids": [trigger_id],
        })

        if not trig:
            continue

        trig = trig[0]
        priority = str(trig["priority"])
        severity = SEVERITY_MAP.get(priority, "Other")
        descr = trig.get("description", "")

        event_entry = {
            "eventid": ev["eventid"],
            "clock": ts,
            "month": month,
            "triggerid": trigger_id,
            "severity": severity,
            "priority": priority,
            "description": descr,
            "hostid": hostid,
            "hostname": hostname,
        }

        cache["months"][month].append(event_entry)

        # Count top triggers (12-month)
        cache["top_triggers"][trigger_id] = cache["top_triggers"].get(trigger_id, 0) + 1

        # Per-host monthly
        h = cache["per_host"].setdefault(hostid, {"host": hostname, "months": {}})
        h["months"][month] = h["months"].get(month, 0) + 1

        # Severity monthly
        sev_bucket = cache["severity"].setdefault(severity, {})
        sev_bucket[month] = sev_bucket.get(month, 0) + 1

        # Investigation (last 30 days)
        if ts >= thirty_days_ago:
            trigger_counter_30d[trigger_id] = trigger_counter_30d.get(trigger_id, 0) + 1

    # Add investigation list
    for tid, cnt in trigger_counter_30d.items():
        if cnt > 40:
            trig = zbx_call("trigger.get", {
                "output": ["triggerid", "description", "priority"],
                "triggerids": [tid],
            })
            if trig:
                t = trig[0]
                cache["investigate"].append({
                    "triggerid": tid,
                    "description": t.get("description", ""),
                    "priority": SEVERITY_MAP.get(str(t.get("priority", "")), "Other"),
                    "count_30d": cnt,
                })

    save_cache(CACHE_NAME, cache)
    touch_cache(CACHE_NAME)


def get_incident_trends(months: int = 2) -> Dict[str, Any]:
    """
    Return processed incident trend data.
    """
    cache = load_cache(CACHE_NAME, default=None)
    if not cache:
        return {"error": "Cache empty. Call refresh_incident_cache first."}

    month_labels = _now_month_labels(months)

    # Top 100 triggers
    top_sorted = sorted(cache["top_triggers"].items(), key=lambda x: x[1], reverse=True)
    top_100 = top_sorted[:100]

    return {
        "month_labels": month_labels,
        "severity": cache["severity"],
        "per_host": cache["per_host"],
        "top_100_triggers": top_100,
        "investigate": cache["investigate"],
        "generated_at": cache["generated_at"],
    }
