from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from config import REPORT_DIR
from routes_core import router as core_router
from routes_netbox import router as netbox_router
from routes_admin import router as admin_router
from workers import start_workers
from log import setup_logging, get_logger
from auth_utils import ensure_admin_credentials
from settings_store import get_effective_settings

# Initialize logging as early as possible
setup_logging()
logger = get_logger(__name__)

# Ensure admin credentials + session secret exist on disk (first boot)
try:
    created, _pwd = ensure_admin_credentials()
    if created:
        logger.warning("Admin password generated on first boot. Read /etc/network-map/admin_password.txt")
except Exception as e:
    logger.warning("Failed to ensure admin credentials: %s", e)

settings = get_effective_settings()

BASE_DIR = Path(__file__).resolve().parent

app = FastAPI()

# Cookie session for /admin login
# If session_secret is missing, SessionMiddleware still needs some key.
_session_secret = settings.session_secret or "dev-unsafe-secret"
app.add_middleware(
    SessionMiddleware,
    secret_key=_session_secret,
    same_site="lax",
    https_only=True,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static mounts (for running without nginx)
static_dir = BASE_DIR / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

# Reports mount
Path(REPORT_DIR).mkdir(parents=True, exist_ok=True)
app.mount("/reports", StaticFiles(directory=REPORT_DIR), name="reports")

# Routers
app.include_router(core_router)
app.include_router(netbox_router)
app.include_router(admin_router)


@app.on_event("startup")
def on_startup():
    logger.info("Starting Network Map application (FastAPI)")
    start_workers()
    logger.info("Background workers started")
