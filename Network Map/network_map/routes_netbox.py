from fastapi import APIRouter, HTTPException

from settings_store import get_effective_settings
from state import get_netbox_vms, get_netbox_services

router = APIRouter()


def _ensure_enabled():
    s = get_effective_settings()
    if not s.enable_netbox:
        raise HTTPException(status_code=503, detail="NetBox integration is disabled")
    if not s.netbox_url or not s.netbox_token:
        raise HTTPException(status_code=503, detail="NetBox is not configured")


@router.get("/api/netbox/vm")
def api_vm_by_name(name: str):
    _ensure_enabled()
    vms = get_netbox_vms()
    for vm in vms.values():
        if vm.get("name") == name or vm.get("display") == name:
            return vm
    raise HTTPException(status_code=404, detail="VM not found")


@router.get("/api/netbox/services-by-vm")
def api_services_by_vm(name: str):
    _ensure_enabled()
    services = get_netbox_services()
    return [
        svc
        for svc in services
        if svc.get("virtual_machine")
        and (
            svc["virtual_machine"].get("name") == name
            or svc["virtual_machine"].get("display") == name
        )
    ]
