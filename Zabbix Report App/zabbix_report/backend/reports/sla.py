from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ..zabbix_client import call as zbx_call


def _format_ts_to_year_month(ts: int) -> str:
    dt = datetime.fromtimestamp(ts, timezone.utc)
    return dt.strftime("%Y-%m")


def get_sla_sli(periods: int = 12, period_from: Optional[int] = None) -> Dict[str, Any]:
    """
    Return SLA/SLI data similar to the old sla-sli.py script, but as a Python
    structure instead of writing JSON to disk. 

    Structure:
    {
      "<slaid>": {
        "sla_name": str,
        "period_from": unix_ts,
        "periods": int,
        "service_data": {
          <serviceid>: {
            "name": str,
            "slo": "99%",
            "month_labels": ["2025-01", ...],
            "monthly_sli": ["100%", "99%", ...]
          },
          ...
        }
      },
      ...
    }
    """
    now_utc = datetime.now(timezone.utc)

    if period_from is None:
        first_day_of_year = datetime(now_utc.year, 1, 1, tzinfo=timezone.utc)
        period_from = int(first_day_of_year.timestamp())

    sla_data: Dict[str, Any] = zbx_call(
        "sla.get",
        {
            "output": "extend",
            "preservekeys": True,
        },
    )

    all_sli_results: Dict[str, Any] = {}

    for sla_id, sla_info in sla_data.items():
        # 1) Get services attached to this SLA
        services: List[Dict[str, Any]] = zbx_call(
            "service.get",
            {
                "output": "extend",
                "slaids": [sla_id],
            },
        )
        if not services:
            continue

        service_map: Dict[int, Dict[str, Any]] = {}
        for svc in services:
            sid = int(svc["serviceid"])
            goodsla = svc.get("goodsla")
            if goodsla is not None:
                try:
                    goodsla = f"{float(goodsla):.0f}%"
                except (TypeError, ValueError):
                    pass
            service_map[sid] = {
                "name": svc.get("name", f"ServiceID {sid}"),
                "slo": goodsla,
            }

        service_ids: List[int] = list(service_map.keys())

        sli_result: Dict[str, Any] = zbx_call(
            "sla.getsli",
            {
                "slaid": sla_id,
                "serviceids": service_ids,
                "periods": periods,
                "period_from": str(period_from),
            },
        )

        period_entries = sli_result.get("periods", [])
        month_labels = [
            _format_ts_to_year_month(int(p["period_from"])) for p in period_entries
        ]

        sli_matrix = sli_result.get("sli", [])

        all_sli_results[sla_id] = {
            "sla_name": sla_info.get("name"),
            "period_from": period_from,
            "periods": periods,
            "service_data": {},
        }

        for svc_index, sid in enumerate(service_ids):
            monthly_sli: List[str] = []
            for period_idx in range(len(sli_matrix)):
                sli_entry = sli_matrix[period_idx][svc_index]
                try:
                    value = float(sli_entry["sli"])
                except (TypeError, ValueError):
                    monthly_sli.append("N/A")
                    continue

                if value < 0:
                    monthly_sli.append("N/A")
                else:
                    monthly_sli.append(f"{value:.0f}%")

            all_sli_results[sla_id]["service_data"][sid] = {
                "name": service_map[sid]["name"],
                "slo": service_map[sid]["slo"],
                "month_labels": month_labels,
                "monthly_sli": monthly_sli,
            }

    return all_sli_results
