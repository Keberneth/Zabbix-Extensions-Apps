from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from auth_utils import verify_password
from log import get_logger
from settings_store import (
    load_settings,
    save_settings,
    masked_settings_for_ui,
    get_effective_settings,
)
from crypto_utils import encrypt_str
from state import get_status
from workers import trigger_netbox_sync, trigger_zabbix_sync, trigger_report_generation

logger = get_logger(__name__)

router = APIRouter(prefix="/api/admin")


def _require_admin(request: Request) -> None:
    if not getattr(request, "session", None):
        raise HTTPException(status_code=500, detail="Session middleware not configured")
    if not request.session.get("admin_authenticated"):
        raise HTTPException(status_code=401, detail="Not authenticated")


class LoginRequest(BaseModel):
    password: str = Field(..., min_length=1)


@router.post("/login")
def admin_login(payload: LoginRequest, request: Request):
    settings = get_effective_settings()
    stored = settings.admin_password_hash
    if not stored:
        # Should not happen if ensure_admin_credentials ran, but stay safe.
        raise HTTPException(status_code=500, detail="Admin password not initialized")

    if not verify_password(payload.password, stored):
        raise HTTPException(status_code=401, detail="Invalid password")

    request.session["admin_authenticated"] = True
    return {"ok": True}


@router.post("/logout")
def admin_logout(request: Request):
    if getattr(request, "session", None):
        request.session.clear()
    return {"ok": True}


@router.get("/me")
def admin_me(request: Request):
    authed = bool(getattr(request, "session", None) and request.session.get("admin_authenticated"))
    return {"authenticated": authed}


@router.get("/settings")
def admin_get_settings(request: Request):
    _require_admin(request)
    return masked_settings_for_ui()


class SettingsUpdate(BaseModel):
    zabbix_url: Optional[str] = ""
    zabbix_token: Optional[str] = None  # plaintext; if None -> keep, if "" -> clear

    netbox_url: Optional[str] = ""
    netbox_token: Optional[str] = None  # plaintext; if None -> keep, if "" -> clear

    enable_netbox: Optional[bool] = True

    zabbix_sync_seconds: Optional[int] = Field(default=None, ge=1)
    netbox_sync_seconds: Optional[int] = Field(default=None, ge=1)
    report_sync_seconds: Optional[int] = Field(default=None, ge=1)


@router.post("/settings")
def admin_update_settings(payload: SettingsUpdate, request: Request):
    _require_admin(request)

    cur = load_settings(force_reload=True)
    upd: Dict[str, Any] = {}

    if payload.zabbix_url is not None:
        upd["zabbix_url"] = (payload.zabbix_url or "").strip()

    if payload.netbox_url is not None:
        upd["netbox_url"] = (payload.netbox_url or "").strip()

    if payload.enable_netbox is not None:
        upd["enable_netbox"] = bool(payload.enable_netbox)

    if payload.zabbix_sync_seconds is not None:
        upd["zabbix_sync_seconds"] = int(payload.zabbix_sync_seconds)

    if payload.netbox_sync_seconds is not None:
        upd["netbox_sync_seconds"] = int(payload.netbox_sync_seconds)

    if payload.report_sync_seconds is not None:
        upd["report_sync_seconds"] = int(payload.report_sync_seconds)

    # Tokens:
    #   None -> keep existing
    #   ""   -> clear
    #   value -> encrypt + save
    if payload.zabbix_token is not None:
        if payload.zabbix_token == "":
            upd["zabbix_token_enc"] = ""
        else:
            upd["zabbix_token_enc"] = encrypt_str(payload.zabbix_token)

    if payload.netbox_token is not None:
        if payload.netbox_token == "":
            upd["netbox_token_enc"] = ""
        else:
            upd["netbox_token_enc"] = encrypt_str(payload.netbox_token)

    merged = dict(cur)
    merged.update(upd)
    save_settings(merged)

    logger.info("Admin updated settings")

    return masked_settings_for_ui()


@router.post("/sync/zabbix")
def admin_sync_zabbix(request: Request):
    _require_admin(request)
    trigger_zabbix_sync()
    return {"ok": True}


@router.post("/sync/netbox")
def admin_sync_netbox(request: Request):
    _require_admin(request)
    trigger_netbox_sync()
    return {"ok": True}


@router.post("/report/generate")
def admin_generate_report(request: Request):
    _require_admin(request)
    trigger_report_generation()
    return {"ok": True}


@router.get("/status")
def admin_status(request: Request):
    _require_admin(request)
    s = get_status()
    return s
