from typing import Any, Iterable
import ipaddress

from config import PRIVATE_NETWORKS


def classify_env(name: Any) -> str:
    """Classify environment from a name/tag string."""
    if not name or not isinstance(name, str):
        return "unknown"
    val = name.lower()
    if any(k in val for k in ["prod", "prd", "produktion", "production"]):
        return "prod"
    if any(k in val for k in ["qa", "quality", "pre-prod", "preproduction", "pre production"]):
        return "qa"
    if any(k in val for k in ["test", "tst"]):
        return "test"
    if any(k in val for k in ["dev", "developer"]):
        return "dev"
    return "unknown"


def _tag_to_str(tag: Any) -> str:
    if isinstance(tag, str):
        return tag
    if isinstance(tag, dict):
        return (
            tag.get("slug")
            or tag.get("name")
            or tag.get("display")
            or tag.get("label")
            or ""
        )
    return str(tag) if tag is not None else ""


def classify_env_from_tags(tags: Any) -> str:
    """Classify environment from NetBox tags.

    Accepts:
      - list of dicts/strings
      - a single dict/string

    If multiple env tags exist, we prefer in this order:
      prod > qa > test > dev
    """
    if not tags:
        return "unknown"

    if isinstance(tags, (str, dict)):
        tags_iter: Iterable[Any] = [tags]
    elif isinstance(tags, (list, tuple, set)):
        tags_iter = tags
    else:
        return "unknown"

    candidates = set()
    for t in tags_iter:
        env = classify_env(_tag_to_str(t))
        if env != "unknown":
            candidates.add(env)

    for pref in ("prod", "qa", "test", "dev"):
        if pref in candidates:
            return pref

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
