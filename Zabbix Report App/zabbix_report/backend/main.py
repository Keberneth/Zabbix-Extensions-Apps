# backend/main.py
from pathlib import Path
from io import BytesIO
import io
import csv
from openpyxl import Workbook   # <-- add this
from . import config

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from . import config
from .reports.sla import get_sla_sli as fetch_sla_sli
from .reports import (
    availability,
    icmp,
    host_info,
    utilization,
    firewall_if_usage,
    uptime_trend,
    incident_trends,
    monthly_report,
)
from .emailer import sender, settings_store
from .logging_utils import setup_logging, get_log_level, set_log_level, tail_log  # 

# Initialize logging as early as possible
setup_logging()

app = FastAPI(title="Zabbix Report App")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
@app.on_event("startup")
async def build_monthly_report_on_startup():
    """
    Build the monthly SLA report once when the application starts.
    If it fails (e.g., Zabbix temporarily unavailable), it is just logged,
    and the user can trigger a rebuild with the 'Update Monthly Report' button.
    """
    import logging

    log = logging.getLogger(__name__)
    try:
        monthly_report.generate_monthly_report()
        log.info("Monthly SLA report generated on startup.")
    except Exception:
        log.exception("Failed to generate monthly SLA report on startup.")

# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------

@app.get("/api/status")
def api_status():
    """
    Lightweight health endpoint for the GUI.
    """
    return {
        "status": "ok",
        "zabbix_url": config.ZABBIX_URL,
    }

# ---------------------------------------------------------------------------
# Monthly SLA report (cached XLSX)
# ---------------------------------------------------------------------------

@app.post("/api/reports/monthly/refresh")
def api_monthly_report_refresh():
    """
    Regenerate the cached monthly SLA report and store it under TMP_DIR.
    """
    try:
        from .reports import monthly_report

        path = monthly_report.generate_monthly_report()
    except Exception as exc:
        raise HTTPException(500, f"Failed to regenerate monthly report: {exc}") from exc

    return {
        "status": "ok",
        "path": str(path),
    }


@app.get("/api/reports/monthly/download")
def api_monthly_report_download():
    """
    Download the cached monthly SLA report (XLSX).
    If it does not exist yet, generate it once first.
    """
    from .reports import monthly_report

    path = monthly_report.get_existing_report_path()
    if path is None:
        try:
            path = monthly_report.generate_monthly_report()
        except Exception as exc:
            raise HTTPException(500, f"Failed to generate monthly report: {exc}") from exc

    if not path.exists():
        raise HTTPException(404, "Monthly report file is missing.")

    return StreamingResponse(
        path.open("rb"),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": 'attachment; filename="monthly_sla_report.xlsx"'
        },
    )

# ---------------------------------------------------------------------------
# SLA / SLI
# ---------------------------------------------------------------------------

@app.get("/api/reports/sla")
def get_sla(periods: int = 12):
    return fetch_sla_sli(periods=periods)  # :contentReference[oaicite:2]{index=2}


@app.get("/api/reports/sla/download")
def download_sla(format: str = "xlsx"):
    from .reports.sla_download import create_sla_xlsx_bytes  # :contentReference[oaicite:3]{index=3}

    if format.lower() != "xlsx":
        raise HTTPException(400, "Only xlsx supported for now")

    data = create_sla_xlsx_bytes(fetch_sla_sli())
    return StreamingResponse(
        data,
        media_type=(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ),
        headers={"Content-Disposition": 'attachment; filename="sla_report.xlsx"'},
    )

# ---------------------------------------------------------------------------
# Availability
# ---------------------------------------------------------------------------

@app.get("/api/reports/availability")
def api_availability(days: int = 30):
    """
    JSON availability per host (de-duplicated across groups).
    Returns one row per host with fields including:
      - host (str)
      - availability (float in [0, 100] or None if no data)
      - group_names, etc.
    """
    return availability.get_availability(days=days)


@app.get("/api/reports/availability/download")
def download_availability(days: int = 30):
    """
    Excel export of availability.
    Only includes 'host' and 'availability' columns.
    """
    rows = availability.get_availability(days=days)

    wb = Workbook()
    ws = wb.active
    ws.title = "Availability"

    # Header
    ws.append(["Host", "Availability (%)"])

    for row in rows:
        host = row.get("host", "")
        avail_raw = row.get("availability")

        # Backend returns strings like "99.9%" or "No data"
        if not isinstance(avail_raw, str):
            display = "No data"
        else:
            val = avail_raw.strip()
            if not val or val.lower() == "no data":
                display = "No data"
            else:
                try:
                    num = float(val.replace("%", "").strip())
                    display = round(num, 1)
                except (TypeError, ValueError):
                    display = "No data"

        ws.append([host, display])

    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)

    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="availability.xlsx"'},
    )



# ---------------------------------------------------------------------------
# ICMP
# ---------------------------------------------------------------------------

@app.get("/api/reports/icmp")
def api_icmp(days: int = 7):   # instead of 30
    return icmp.get_icmp_history(days=days)


@app.get("/api/reports/icmp/download")
def download_icmp(days: int = 30):
    docs = icmp.get_icmp_history(days=days)
    buf = io.StringIO()
    w = csv.writer(buf)

    header = [
        "hostid",
        "host",
        "name",
        "clock",
        "value",
        "itemid",
        "item_name",
        "key_",
    ]
    w.writerow(header)

    for d in docs:
        item = d.get("item", {})
        for h in d.get("history", []):
            w.writerow(
                [
                    d.get("hostid", ""),
                    d.get("host", ""),
                    d.get("name", ""),
                    h.get("clock", ""),
                    h.get("value", ""),
                    item.get("itemid", ""),
                    item.get("name", ""),
                    item.get("key_", ""),
                ]
            )

    buf.seek(0)
    byte_buf = BytesIO(buf.getvalue().encode("utf-8"))
    return StreamingResponse(
        byte_buf,
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="icmp_history.csv"'},
    )

# ---------------------------------------------------------------------------
# Host information
# ---------------------------------------------------------------------------

@app.get("/api/reports/host-info")
def api_host_info():
    """
    Static host inventory info (OS, RAM, cores, disks). :contentReference[oaicite:6]{index=6}
    """
    return host_info.get_host_info()

# ---------------------------------------------------------------------------
# Service utilization (CPU / RAM)
# ---------------------------------------------------------------------------

@app.get("/api/reports/utilization")
def api_utilization(days: int = 30):
    """
    Per-host CPU/RAM utilization for processes/services. :contentReference[oaicite:7]{index=7}
    """
    return utilization.get_service_utilization(days=days)

# ---------------------------------------------------------------------------
# Firewall interface usage
# ---------------------------------------------------------------------------

@app.get("/api/reports/firewall-if-usage")
def api_firewall_if_usage(days: int = 30):
    """
    Bits sent history for FW interfaces. :contentReference[oaicite:8]{index=8}
    """
    return firewall_if_usage.get_firewall_interface_usage(days=days)

# ---------------------------------------------------------------------------
# Uptime trend (12-month rolling, using persistent cache)
# ---------------------------------------------------------------------------

@app.get("/api/reports/uptime-trend")
def get_uptime_trend(months: int = 12, refresh: bool = True):
    """
    Returns last `months` of uptime per host from cache, optionally refreshing
    cache using recent availability data. :contentReference[oaicite:9]{index=9}
    """
    if refresh:
        uptime_trend.refresh_from_recent(days=35)
    return uptime_trend.get_uptime_trend(months=months)


@app.get("/api/reports/uptime-trend/download")
def download_uptime_trend(months: int = 12, format: str = "csv"):
    if format.lower() != "csv":
        raise HTTPException(400, "Only csv supported for uptime trend report")

    uptime_trend.refresh_from_recent(days=35)
    data = uptime_trend.get_uptime_trend(months=months)

    buf = io.StringIO()
    writer = csv.writer(buf)

    month_labels = data["month_labels"]
    header = ["hostid", "host", "group_name"] + month_labels
    writer.writerow(header)

    for h in data["hosts"]:
        row = [h["hostid"], h["host"], h["group_name"]] + h["monthly_uptime"]
        writer.writerow(row)

    buf.seek(0)
    byte_buf = BytesIO(buf.getvalue().encode("utf-8"))

    filename = f"uptime_trend_{months}m.csv"
    return StreamingResponse(
        byte_buf,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

# ---------------------------------------------------------------------------
# Incident trends (12-month + 30-day “needs investigation”)
# ---------------------------------------------------------------------------

@app.get("/api/reports/incidents/refresh")
def refresh_incidents(months: int = 12):
    incident_trends.refresh_incident_cache(months=months)  # :contentReference[oaicite:10]{index=10}
    return {"status": "ok"}


@app.get("/api/reports/incidents")
def get_incidents(months: int = 12, refresh: bool = True):
    """
    Try to refresh cache, but never crash the API if Zabbix returns 500.
    GUI will still show whatever is in cache (or 'cache empty' message).
    """
    if refresh:
        try:
            incident_trends.refresh_incident_cache(months=months)
        except Exception as exc:
            logger.exception("Failed to refresh incident cache: %s", exc)
            # fall through and return existing cache (if any)

    return incident_trends.get_incident_trends(months=months)


@app.get("/api/reports/incidents/download")
def download_incidents(months: int = 12):
    data = incident_trends.get_incident_trends(months)

    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["triggerid", "count"])
    for tid, cnt in data.get("top_100_triggers", []):
        w.writerow([tid, cnt])

    buf.seek(0)
    byte_buf = BytesIO(buf.getvalue().encode("utf-8"))

    return StreamingResponse(
        byte_buf,
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="incident_top100.csv"'},
    )

# ---------------------------------------------------------------------------
# Email settings + reporting
# ---------------------------------------------------------------------------

@app.get("/api/email/settings")
def get_email_settings():
    return settings_store.get_settings()  # :contentReference[oaicite:11]{index=11}


@app.put("/api/email/settings")
def update_email_settings(settings: dict):
    settings_store.save_settings(settings)
    return {"status": "ok"}


# Accept POST as well so the frontend can use either.
@app.post("/api/email/settings")
def update_email_settings_post(settings: dict):
    settings_store.save_settings(settings)
    return {"status": "ok"}


@app.post("/api/email/send-report")
def send_report(payload: dict):
    """
    Generic email-sending entrypoint, expects the payload format described
    in sender.send_report_email.
    """
    sender.send_report_email(payload)  # :contentReference[oaicite:12]{index=12}
    return {"status": "sent"}


@app.post("/api/email/send-sla")
def send_sla_email():
    """
    Convenience endpoint used by the GUI: send latest SLA report to default
    recipients stored in email settings (field: to_addr).
    """
    settings = settings_store.get_settings()
    recipients = settings.get("to_addr") or []
    if not recipients:
        raise HTTPException(
            400, "No default recipients (to_addr) configured in email settings"
        )

    payload = {
        "report_type": "sla",
        "format": "xlsx",
        "to": recipients,
        "subject": "SLA report",
        "body": "Zabbix SLA/SLI report.",
    }
    sender.send_report_email(payload)
    return {"status": "sent"}

# ---------------------------------------------------------------------------
# Logging API
# ---------------------------------------------------------------------------

@app.get("/api/logs")
def api_get_logs(lines: int = 200):
    return {
        "level": get_log_level(),
        "lines": tail_log(lines),
    }


@app.get("/api/logs/level")
def api_get_log_level():
    return {"level": get_log_level()}


@app.put("/api/logs/level")
def api_set_log_level(payload: dict):
    level = payload.get("level")
    if not level:
        raise HTTPException(400, "Missing 'level' in payload")

    new_level = set_log_level(str(level))
    return {"level": new_level}

# ---------------------------------------------------------------------------
# Static frontend
# ---------------------------------------------------------------------------

FRONTEND_DIR = config.APP_ROOT / "frontend"

app.mount(
    "/",
    StaticFiles(directory=str(FRONTEND_DIR), html=True),
    name="frontend",
)
