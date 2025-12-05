import smtplib
from email.message import EmailMessage

from .settings_store import get_settings
from backend.reports.sla_download import create_sla_xlsx_bytes
from backend.reports.sla import create_sla_report
from backend.reports.availability import create_availability_report
from backend.reports.uptime_trend import create_uptime_trend_report
from backend.reports.incident_trends import create_incident_trends_report
from backend.reports.icmp import create_icmp_report
from backend.reports.host_info import create_host_info_report
from backend.reports.firewall_if_usage import create_firewall_if_usage_report
from backend.reports.utilization import create_utilization_report

def send_report_email(payload: dict) -> None:
    """
    Send a report by email.

    payload example:
    {
        "report_type": "sla",
        "format": "xlsx",
        "to": ["user@example.com"],
        "subject": "SLA report",
        "body": "See attached report.",
        "password": "smtp-password",   # optional; only used if username is configured
        "periods": 12,                 # optional; SLA periods
        "filename": "sla_report.xlsx"  # optional
    }

    Authentication is only attempted if a username is configured in email settings.
    This allows using mail proxies/relays that do not require username/password.
    """
    settings = get_settings()

    # Recipients
    to_addrs = payload.get("to")
    if not to_addrs:
        raise ValueError("No recipients specified")

    report_type = payload.get("report_type", "sla")
    fmt = payload.get("format", "xlsx")

    # Currently only SLA/XLSX is implemented
    if report_type == "sla" and fmt == "xlsx":
        periods = int(payload.get("periods", 12))
        # Let sla_download fetch SLA data itself if not provided
        data = create_sla_xlsx_bytes(periods=periods)
        filename = payload.get("filename", "sla_report.xlsx")
    else:
        raise ValueError("Unsupported report_type/format combination")

    # Basic message
    msg = EmailMessage()
    msg["Subject"] = payload.get("subject", "Zabbix report")

    from_addr = settings.get("from_addr")
    if not from_addr:
        raise ValueError("Missing from_addr in email settings")
    msg["From"] = from_addr

    msg["To"] = ", ".join(to_addrs)
    msg.set_content(payload.get("body", "See attached report."))

    # Attachment
    binary_data = data.getvalue() if hasattr(data, "getvalue") else data
    msg.add_attachment(
        binary_data,
        maintype="application",
        subtype="vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=filename,
    )

    # SMTP connection
    smtp_host = settings.get("smtp_host")
    smtp_port = settings.get("smtp_port", 25)
    if not smtp_host:
        raise ValueError("Missing smtp_host in email settings")

    with smtplib.SMTP(smtp_host, smtp_port) as s:
        # Optional STARTTLS
        if settings.get("use_tls", True):
            s.starttls()

        # Optional authentication:
        # Only attempt login if username is configured – this supports
        # mail proxies/relays that do not require auth.
        username = settings.get("username") or ""
        if username:
            password = payload.get("password") or settings.get("password") or ""
            s.login(username, password)

        s.send_message(msg)
