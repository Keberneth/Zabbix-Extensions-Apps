# backend/main.py
from pathlib import Path
from io import BytesIO
import io
import csv
import logging
import threading

from openpyxl import Workbook
from fastapi import FastAPI, HTTPException, BackgroundTasks
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
from .logging_utils import setup_logging, get_log_level, set_log_level, tail_log

# Initialize logging as early as possible
setup_logging()
logger = logging.getLogger(__name__)

app = FastAPI(title="Zabbix Report App")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Startup: schedule monthly report build in background (non-blocking)
# ---------------------------------------------------------------------------

@app.on_event("startup")
async def schedule_monthly_report_build():
    """
    Schedule monthly report generation in a background thread so that
    application startup is not blocked.
    """
    def _worker():
        try:
            monthly_report.generate_monthly_report()
            logger.info("Monthly SLA report generated on startup (background).")
        except Exception:
            logger.exception("Failed to generate monthly SLA report on startup.")

    t = threading.Thread(target=_worker, daemon=True)
    t.start()

# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------

@app.get("/api/status")
def api_status():
    return {
        "status": "ok",
        "zabbix_url": config.ZABBIX_URL,
    }

# ---------------------------------------------------------------------------
# Monthly SLA report (cached XLSX)
# ---------------------------------------------------------------------------

@app.post("/api/reports/monthly/refresh")
def api_monthly_report_refresh(background_tasks: BackgroundTasks):
    """
    Regenerate the cached monthly SLA report asynchronously.

    The work is scheduled in the background and this endpoint returns
    immediately to avoid 504s from Nginx.
    """
    background_tasks.add_task(monthly_report.generate_monthly_report)
    return {"status": "scheduled"}


@app.get("/api/reports/monthly/download")
def api_monthly_report_download():
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
    return fetch_sla_sli(periods=periods)  # :contentReference[oaicite:0]{index=0}


@app.get("/api/reports/sla/download")
def download_sla(format: str = "xlsx"):
    from .reports.sla_download import create_sla_xlsx_bytes  # :contentReference[oaicite:1]{index=1}

    if format.lower() != "xlsx":
        raise HTTPException(400, "Only xlsx supported for now")

    data = create_sla_xlsx_bytes(fetch_sla_sli())
    return StreamingResponse(
        data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="sla_report.xlsx"'},
    )

# ---------------------------------------------------------------------------
# Availability
# ---------------------------------------------------------------------------

@app.get("/api/reports/availability")
def api_availability(days: int = 30):
    """
    JSON availability per host (de-duplicated across groups).
    """
    return availability.get_availability(days=days)  # :contentReference[oaicite:2]{index=2}


@app.get("/api/reports/availability/download")
def download_availability(days: int = 30):
    rows = availability.get_availability(days=days)

    wb = Workbook()
    ws = wb.active
    ws.title = "Availability"

    ws.append(["Host", "Availability (%)"])

    for row in rows:
        host = row.get("host", "")
        avail_raw = row.get("availability")

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
def api_icmp(days: int = 7):
    return icmp.get_icmp_history(days=days)  # :contentReference[oaicite:3]{index=3}


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
    return host_info.get_host_info()  # :contentReference[oaicite:4]{index=4}

# ---------------------------------------------------------------------------
# Utilization
# ---------------------------------------------------------------------------

@app.get("/api/reports/utilization")
def api_utilization(days: int = 30):
    return utilization.get_service_utilization(days=days)  # :contentReference[oaicite:5]{index=5}

# ---------------------------------------------------------------------------
# Firewall interface usage
# ---------------------------------------------------------------------------

@app.get("/api/reports/firewall-if-usage")
def api_firewall_if_usage(days: int = 30):
    return firewall_if_usage.get_firewall_interface_usage(days=days)  # :contentReference[oaicite:6]{index=6}

# ---------------------------------------------------------------------------
# Uptime trend
# ---------------------------------------------------------------------------

@app.get("/api/reports/uptime-trend")
def get_uptime_trend(months: int = 12, refresh: bool = True):
    if refresh:
        uptime_trend.refresh_from_recent(days=35)  # :contentReference[oaicite:7]{index=7}
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
# Incident trends
# ---------------------------------------------------------------------------

@app.get("/api/reports/incidents/refresh")
def refresh_incidents(months: int = 12):
    """
    Force a refresh of the incident cache.

    If Zabbix returns an error (HTTP 500 or API error), return 502 with
    a readable message instead of a Python stack trace.
    """
    try:
        incident_trends.refresh_incident_cache(months=months)
    except Exception as exc:
        logger.exception("Failed to refresh incident cache from Zabbix")
        # 502 = bad gateway / upstream error, which is exactly what this is
        raise HTTPException(
            status_code=502,
            detail=f"Failed to refresh incident data from Zabbix: {exc}"
        )
    return {"status": "ok"}


@app.get("/api/reports/incidents")
def get_incidents(months: int = 12, refresh: bool = True):
    """
    Optionally refresh the cache, but always return a JSON structure
    instead of raising. If refresh fails, we return whatever is in
    cache plus an 'error' field.
    """
    error: Optional[str] = None

    if refresh:
        try:
            incident_trends.refresh_incident_cache(months=months)
        except Exception as exc:
            logger.exception("Failed to refresh incident cache from Zabbix")
            error = f"Failed to refresh incident data from Zabbix: {exc}"

    data = incident_trends.get_incident_trends(months=months)

    # If cache was empty AND refresh failed, data will already contain
    # {"error": "Cache empty ..."}; we just append the more detailed reason.
    if error:
        data.setdefault("error_detail", error)

    return data


# ---------------------------------------------------------------------------
# Email settings + reporting
# ---------------------------------------------------------------------------

@app.get("/api/email/settings")
def get_email_settings():
    return settings_store.get_settings()  # :contentReference[oaicite:9]{index=9}


@app.put("/api/email/settings")
def update_email_settings(settings: dict):
    settings_store.save_settings(settings)
    return {"status": "ok"}


@app.post("/api/email/settings")
def update_email_settings_post(settings: dict):
    settings_store.save_settings(settings)
    return {"status": "ok"}


@app.post("/api/email/send-report")
def send_report(payload: dict):
    sender.send_report_email(payload)  # :contentReference[oaicite:10]{index=10}
    return {"status": "sent"}


@app.post("/api/email/send-sla")
def send_sla_email():
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
