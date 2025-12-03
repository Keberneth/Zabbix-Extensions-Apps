import time
import statistics
from typing import Any, Dict, List, Optional, Tuple

from ..zabbix_client import call as zbx_call


def _infer_interval_from_history(tstamps: List[int]) -> Optional[int]:
    """
    Infer the sampling interval from timestamps, based on the logic in the
    original avalibility-report-dynamic.py.
    """
    if len(tstamps) < 2:
        return None
    deltas = [tstamps[i] - tstamps[i - 1] for i in range(1, len(tstamps))]
    deltas = [d for d in deltas if d > 0]
    if not deltas:
        return None

    if len(deltas) >= 10:
        p90 = statistics.quantiles(deltas, n=10)[8]
    else:
        p90 = max(deltas)

    core = [d for d in deltas if d <= p90] or deltas
    med = int(statistics.median(core))
    if med <= 0:
        return None

    common = [30, 60, 120, 300, 600, 900, 1800, 3600]
    best = min(common, key=lambda c: abs(c - med))
    if abs(best - med) <= max(2, int(med * 0.1)):
        return best
    return med


def _paginate_history(item_id: str, start: int, end: int) -> List[int]:
    """
    Collect all timestamps for numeric history (type=3) for agent.ping
    between start and end.
    """
    cursor = start
    limit = 10000
    timestamps: List[int] = []

    while True:
        res = zbx_call(
            "history.get",
            {
                "itemids": item_id,
                "history": 3,
                "time_from": cursor,
                "time_till": end,
                "sortfield": "clock",
                "sortorder": "ASC",
                "limit": limit,
            },
        )
        if not res:
            break
        for r in res:
            timestamps.append(int(r["clock"]))
        if len(res) < limit:
            break
        cursor = timestamps[-1] + 1

    return timestamps


def _count_missing_samples(
    tstamps: List[int], start: int, end: int, step: int
) -> Tuple[int, int, int]:
    """
    Count observed and missing samples for a series with roughly fixed interval.
    """
    if not tstamps:
        return 0, 0, 0

    tstamps = sorted(tstamps)
    observed = len(tstamps)
    missing = 0

    # gap from window start
    missing += max(0, (tstamps[0] - start) // step)

    # interior gaps
    for i in range(1, observed):
        gap = tstamps[i] - tstamps[i - 1]
        if gap > step:
            missing += (gap // step) - 1

    # tail gap
    missing += max(0, (end - tstamps[-1]) // step)

    expected = observed + missing
    return observed, missing, expected


def get_availability(
    group_ids: Optional[List[str]] = None,
    days: int = 30,
) -> List[Dict[str, Any]]:
    """
    Compute host availability based on agent.ping items.

    Important: even if a host is in multiple groups, the result will contain
    that host only once. Group membership is aggregated into lists:

      "groupids": [ ... ],
      "group_names": [ ... ]

    Returned structure (one element per host):

    [
      {
        "hostid": str,
        "host": str,
        "groupids": [str, ...],
        "group_names": [str, ...],
        "availability": "99.9%" or "No data",
        "window_start": int,
        "window_end": int,
        "interval_s": int or None,
        "observed_samples": int,
        "missing_samples": int,
        "expected_samples": int,
      },
      ...
    ]
    """
    end_time = int(time.time())
    start_time = end_time - days * 24 * 60 * 60

    if group_ids is None:
        groups = zbx_call("hostgroup.get", {"output": ["groupid", "name"]})
    else:
        groups = zbx_call(
            "hostgroup.get",
            {
                "output": ["groupid", "name"],
                "groupids": group_ids,
            },
        )

    # hostid -> row (so we only compute availability once per host)
    host_rows: Dict[str, Dict[str, Any]] = {}

    for g in groups:
        gid = g["groupid"]
        gname = g["name"]

        hosts = zbx_call(
            "host.get",
            {
                "groupids": gid,
                "output": ["hostid", "host"],
            },
        )

        for h in hosts:
            host_id = h["hostid"]
            host_name = h["host"]

            # If we've already processed this host, just add group info and skip
            existing = host_rows.get(host_id)
            if existing is not None:
                if gid not in existing["groupids"]:
                    existing["groupids"].append(gid)
                if gname not in existing["group_names"]:
                    existing["group_names"].append(gname)
                continue

            # New host: compute availability once
            items = zbx_call(
                "item.get",
                {
                    "hostids": host_id,
                    "search": {"key_": "agent.ping"},
                    "output": ["itemid", "key_", "delay"],
                },
            )
            if not items:
                availability = "No data"
                observed = missing = expected = 0
                step = None
            else:
                item = items[0]
                item_id = item["itemid"]
                timestamps = _paginate_history(item_id, start_time, end_time)

                if not timestamps:
                    availability = "No data"
                    observed = missing = expected = 0
                    step = None
                else:
                    step = _infer_interval_from_history(timestamps) or 60
                    observed, missing, expected = _count_missing_samples(
                        timestamps, start_time, end_time, step
                    )
                    total_considered = observed + missing
                    if total_considered <= 0:
                        availability = "No data"
                    else:
                        pct = (observed / total_considered) * 100.0
                        availability = f"{pct:.1f}%"

            row = {
                "hostid": host_id,
                "host": host_name,
                "groupids": [gid],
                "group_names": [gname],
                "availability": availability,
                "window_start": start_time,
                "window_end": end_time,
                "interval_s": step,
                "observed_samples": observed,
                "missing_samples": missing,
                "expected_samples": expected,
            }

            host_rows[host_id] = row

    # One row per host, already de-duplicated
    return list(host_rows.values())
