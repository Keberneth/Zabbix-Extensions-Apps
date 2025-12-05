# backend/reports/monthly_report.py
"""
Monthly SLA report caching.

- Uses existing SLA/SLI logic and XLSX builder.
- Stores a single XLSX file in the application temp/cache directory
  (config.TMP_DIR, i.e. /opt/zabbix_report/data/tmp).
- Can be regenerated on demand or at application startup.
"""

from pathlib import Path
from typing import Optional

from ..config import TMP_DIR

# Single cached report file in the app's temp/cache area
REPORT_FILENAME = "monthly_sla_report.xlsx"
REPORT_PATH: Path = TMP_DIR / REPORT_FILENAME


def generate_monthly_report() -> Path:
    """
    Build the SLA/SLI XLSX report and store it in TMP_DIR.

    Returns:
        Path to the generated XLSX file.
    """
    # Lazy imports to avoid circular imports during package initialization
    from .sla import get_sla_sli
    from .sla_download import create_sla_xlsx_bytes

    # Reuse the existing SLA data + XLSX builder
    sla_data = get_sla_sli()
    buf = create_sla_xlsx_bytes(sla_data)

    # Write atomically: .tmp then rename to final
    tmp_path = REPORT_PATH.with_suffix(".xlsx.tmp")
    tmp_path.parent.mkdir(parents=True, exist_ok=True)

    with tmp_path.open("wb") as f:
        f.write(buf.getvalue())

    tmp_path.replace(REPORT_PATH)
    return REPORT_PATH


def get_existing_report_path() -> Optional[Path]:
    """
    Return the path to the cached report if it exists, else None.
    """
    if REPORT_PATH.exists():
        return REPORT_PATH
    return None
