# main.py
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
from io import BytesIO

from .reports.sla import fetch_sla_sli
from .reports import availability, icmp, host_info, utilization, firewall_if_usage, uptime_trend, incident_trends
from .emailer import sender, settings_store

# NEW: logging utils
from .logging_utils import setup_logging, get_log_level, set_log_level, tail_log

# Initialize logging as early as possible
setup_logging()

app = FastAPI(title="Zabbix Report App")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- SLA -----------------------------------------------------------------

@app.get("/api/reports/sla")
def get_sla(periods: int = 12):
    return fetch_sla_sli(periods=periods)

@app.get("/api/reports/sla/download")
def download_sla(format: str = "xlsx"):
    from .reports.sla_download import create_sla_xlsx_bytes
    if format != "xlsx":
        raise HTTPException(400, "Only xlsx supported for now")
    data = create_sla_xlsx_bytes(fetch_sla_sli())
    return StreamingResponse(
        data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="sla_report.xlsx"'}
    )

# (existing report + email endpoints unchanged)… 

# --- Email settings -------------------------------------------------------

@app.get("/api/email/settings")
def get_email_settings():
    return settings_store.get_settings()

@app.put("/api/email/settings")
def update_email_settings(settings: dict):
    settings_store.save_settings(settings)
    return {"status": "ok"}

@app.post("/api/email/send-report")
def send_report(payload: dict):
    sender.send_report_email(payload)
    return {"status": "sent"}

# --- Uptime trend ---------------------------------------------------------

@app.get("/api/reports/uptime-trend")
def get_uptime_trend(months: int = 12, refresh: bool = True):
    if refresh:
        uptime_trend.refresh_from_recent(days=35)
    return uptime_trend.get_uptime_trend(months=months)

@app.get("/api/reports/uptime-trend/download")
def download_uptime_trend(months: int = 12, format: str = "csv"):
    if format.lower() != "csv":
        raise HTTPException(400, "Only csv supported for uptime trend report")

    uptime_trend.refresh_from_recent(days=35)
    data = uptime_trend.get_uptime_trend(months=months)

    import csv
    import io

    buf = io.StringIO()
    writer = csv.writer(buf)

    month_labels = data["month_labels"]
    header = ["hostid", "host", "group_name"] + month_labels
    writer.writerow(header)

    for h in data["hosts"]:
        row = [h["hostid"], h["host"], h["group_name"]] + h["monthly_uptime"]
        writer.writerow(row)

    buf.seek(0)
    byte_buf = io.BytesIO(buf.getvalue().encode("utf-8"))

    filename = f"uptime_trend_{months}m.csv"
    return StreamingResponse(
        byte_buf,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

# --- Incident trends ------------------------------------------------------

@app.get("/api/reports/incidents/refresh")
def refresh_incidents(months: int = 12):
    incident_trends.refresh_incident_cache(months=months)
    return {"status": "ok"}

@app.get("/api/reports/incidents")
def get_incidents(months: int = 12):
    return incident_trends.get_incident_trends(months=months)

@app.get("/api/reports/incidents/download")
def download_incidents(months: int = 12):
    import csv, io
    data = incident_trends.get_incident_trends(months)

    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["triggerid", "count"])
    for tid, cnt in data["top_100_triggers"]:
        w.writerow([tid, cnt])

    buf.seek(0)
    byte_buf = io.BytesIO(buf.getvalue().encode("utf-8"))

    return StreamingResponse(
        byte_buf,
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="incident_top100.csv"'},
    )

# --- Logging API ----------------------------------------------------------

@app.get("/api/logs")
def api_get_logs(lines: int = 200):
    """
    Return the last `lines` log lines plus current log level.

    GUI can show this as a scrollable text area.
    """
    return {
        "level": get_log_level(),
        "lines": tail_log(lines),
    }


@app.get("/api/logs/level")
def api_get_log_level():
    """
    Get current log level.
    """
    return {"level": get_log_level()}


@app.put("/api/logs/level")
def api_set_log_level(payload: dict):
    """
    Set log level. Example payload: {"level": "INFO"}.

    Supported values: DEBUG, INFO, WARNING, ERROR, CRITICAL (case-insensitive).
    """
    level = payload.get("level")
    if not level:
        raise HTTPException(400, "Missing 'level' in payload")

    new_level = set_log_level(str(level))
    return {"level": new_level}
