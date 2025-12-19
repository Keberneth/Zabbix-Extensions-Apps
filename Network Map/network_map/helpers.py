from typing import Any
import ipaddress

from config import PRIVATE_NETWORKS


def classify_env(name: Any) -> str:
    """
    Classify environment from a role/display name OR a list of tag names.
    Safe if 'name' is not a string.
    """
    if not name:
        return "unknown"

    # NEW: if a list/tuple/set of tag strings is provided, try each item
    if isinstance(name, (list, tuple, set)):
        for item in name:
            env = classify_env(item)
            if env != "unknown":
                return env
        return "unknown"

    if not isinstance(name, str):
        return "unknown"

    val = name.lower()
    if any(k in val for k in ["prod", "prd", "produktion", "production"]):
        return "prod"
    if any(k in val for k in ["dev", "developer"]):
        return "dev"
    if any(k in val for k in ["test", "tst"]):
        return "test"
    if any(k in val for k in ["qa", "quality", "pre-prod", "preproduction", "pre production"]):
        return "qa"
    return "unknown"

def is_public_ip(ip: str) -> bool:
    try:
        ip_obj = ipaddress.ip_address(ip)
        return not any(ip_obj in net for net in PRIVATE_NETWORKS)
    except ValueError:
        return False


def is_internal_ip(ip: str) -> bool:
    try:
        ip_obj = ipaddress.ip_address(ip)
        return any(ip_obj in net for net in PRIVATE_NETWORKS)
    except ValueError:
        return False
