from typing import Any
import ipaddress

from config import PRIVATE_NETWORKS


def classify_env(name: Any) -> str:
    """
    Classify environment from a role/display name.
    Safe if 'name' is not a string.
    """
    if not name:
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


def classify_env_from_tags(tags: Any) -> str:
    """
    Classify environment from a NetBox tag list.
    Accepts list of tag dicts/strings or a single tag dict/string.
    """
    if not tags:
        return "unknown"

    if isinstance(tags, (str, dict)):
        tags = [tags]

    if not isinstance(tags, (list, tuple, set)):
        return "unknown"

    for tag in tags:
        if isinstance(tag, str):
            candidate = tag
        elif isinstance(tag, dict):
            candidate = (
                tag.get("name")
                or tag.get("slug")
                or tag.get("display")
                or tag.get("label")
                or ""
            )
        else:
            candidate = ""

        env = classify_env(candidate)
        if env != "unknown":
            return env

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

