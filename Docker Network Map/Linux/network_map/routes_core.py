from pathlib import Path
import io
import zipfile

from fastapi import APIRouter, HTTPException
from fastapi.responses import RedirectResponse, StreamingResponse

from config import REPORT_DIR
from state import get_cached_map, get_last_updated

router = APIRouter()

BASE_DIR = Path(__file__).resolve().parent


@router.get("/", include_in_schema=False)
def serve_index():
    # Just redirect "/" to the static index
    return RedirectResponse(url="/static/index.html")


@router.get("/api/status")
def api_status():
    return {"last_updated": get_last_updated()}


@router.get("/api/network_map")
def api_network_map():
    return get_cached_map()


@router.get("/api/reports")
def list_reports():
    report_dir = Path(REPORT_DIR)
    if not report_dir.exists():
        raise HTTPException(status_code=500, detail="Report directory not found")
    files = []
    for file in report_dir.iterdir():
        if file.suffix.lower() in [".csv", ".xlsx", ".drawio"]:
            mtime = file.stat().st_mtime
            mtime_str = (
                __import__("datetime")
                .datetime.fromtimestamp(mtime)
                .strftime("%Y-%m-%d %H:%M")
            )
            files.append({"name": file.name, "mtime": mtime_str})
    return files


@router.get("/api/reports/download_zip")
def download_reports_zip():
    report_dir = Path(REPORT_DIR)
    if not report_dir.exists():
        raise HTTPException(status_code=500, detail="Report directory not found")

    mem_zip = io.BytesIO()
    try:
        with zipfile.ZipFile(mem_zip, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
            for file in report_dir.iterdir():
                if file.suffix.lower() in [".csv", ".xlsx", ".drawio"]:
                    zf.write(file, arcname=file.name)
        mem_zip.seek(0)
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error creating zip file: {str(e)}"
        )

    return StreamingResponse(
        mem_zip,
        media_type="application/zip",
        headers={"Content-Disposition": "attachment; filename=network_reports.zip"},
    )
