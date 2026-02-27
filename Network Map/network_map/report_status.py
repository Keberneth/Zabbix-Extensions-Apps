import threading
from datetime import datetime
from typing import Any, Dict, Optional

_status_lock = threading.Lock()
_status: Dict[str, Any] = {
    "running": False,
    "last_run_start": None,
    "last_run_end": None,
    "last_run_ok": None,
    "last_error": None,
}


def report_started() -> None:
    """Mark that a report run has started."""
    now = datetime.utcnow()
    with _status_lock:
        _status["running"] = True
        _status["last_run_start"] = now
        _status["last_run_end"] = None
        _status["last_run_ok"] = None
        _status["last_error"] = None


def report_finished(ok: bool, error: Optional[str] = None) -> None:
    """Mark that a report run has finished."""
    now = datetime.utcnow()
    with _status_lock:
        _status["running"] = False
        _status["last_run_end"] = now
        _status["last_run_ok"] = ok
        _status["last_error"] = error


def get_status() -> Dict[str, Any]:
    """Return a JSON-serializable snapshot of report status."""
    with _status_lock:
        def fmt(dt):
            return dt.isoformat() + "Z" if isinstance(dt, datetime) else None

        return {
            "running": _status["running"],
            "last_run_start": fmt(_status["last_run_start"]),
            "last_run_end": fmt(_status["last_run_end"]),
            "last_run_ok": _status["last_run_ok"],
            "last_error": _status["last_error"],
        }

