from __future__ import annotations

from typing import Dict, List, Any, Optional

import requests

from log import get_logger
from settings_store import get_effective_settings, EffectiveSettings

logger = get_logger(__name__)


def _headers(token: str) -> Dict[str, str]:
    return {"Authorization": f"Token {token}", "Accept": "application/json"}


def fetch_netbox_vms(settings: Optional[EffectiveSettings] = None) -> Dict[str, Any]:
    """Fetch VMs from NetBox.

    Returns an empty dict when NetBox is disabled or not configured.
    """
    settings = settings or get_effective_settings()
    if not settings.enable_netbox:
        logger.info("NetBox integration disabled; skipping VM fetch")
        return {}

    if not settings.netbox_url or not settings.netbox_token:
        logger.warning("NetBox not configured (url/token missing); skipping VM fetch")
        return {}

    vms: Dict[str, Any] = {}
    url = f"{settings.netbox_url.rstrip('/')}/api/virtualization/virtual-machines/"
    headers = _headers(settings.netbox_token)
    params = {"limit": 1000}

    while url:
        r = requests.get(url, headers=headers, params=params, verify=False, timeout=60)
        r.raise_for_status()
        js = r.json()
        for vm in js.get("results", []):
            vms[str(vm.get("id"))] = vm
        url = js.get("next")
        params = None

    return vms


def fetch_netbox_services(settings: Optional[EffectiveSettings] = None) -> List[Dict[str, Any]]:
    """Fetch services from NetBox.

    Returns an empty list when NetBox is disabled or not configured.
    """
    settings = settings or get_effective_settings()
    if not settings.enable_netbox:
        logger.info("NetBox integration disabled; skipping services fetch")
        return []

    if not settings.netbox_url or not settings.netbox_token:
        logger.warning("NetBox not configured (url/token missing); skipping services fetch")
        return []

    svcs: List[Dict[str, Any]] = []
    url = f"{settings.netbox_url.rstrip('/')}/api/ipam/services/"
    headers = _headers(settings.netbox_token)
    params = {"limit": 1000}

    while url:
        r = requests.get(url, headers=headers, params=params, verify=False, timeout=60)
        r.raise_for_status()
        js = r.json()
        svcs.extend(js.get("results", []))
        url = js.get("next")
        params = None

    return svcs
