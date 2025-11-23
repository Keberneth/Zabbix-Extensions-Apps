from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from config import REPORT_DIR
from routes_core import router as core_router
from routes_netbox import router as netbox_router
from routes_zabbix import router as zabbix_router
from workers import start_workers

BASE_DIR = Path(__file__).resolve().parent

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static mounts
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
app.mount("/reports", StaticFiles(directory=REPORT_DIR), name="reports")

# Routers
app.include_router(core_router)
app.include_router(netbox_router)
app.include_router(zabbix_router)


@app.on_event("startup")
def on_startup():
    start_workers()
