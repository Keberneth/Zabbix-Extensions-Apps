"""Admin authentication utilities.

We store a PBKDF2 hash of the admin password in settings.json.
We do NOT store plaintext passwords in settings.json.

For first boot, if no admin password exists, we generate one and write it to
/etc/network-map/admin_password.txt (permission 600) so the installer/user can retrieve it.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
from pathlib import Path
from typing import Tuple

from config import ADMIN_PASSWORD_FILE
from log import get_logger
from settings_store import load_settings, save_settings

logger = get_logger(__name__)


def _b64e(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode("ascii").rstrip("=")


def _b64d(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode((s + pad).encode("ascii"))


def hash_password(password: str, *, iterations: int = 200_000) -> str:
    """Return a PBKDF2-SHA256 password hash string."""
    if password is None:
        password = ""
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"pbkdf2_sha256${iterations}${_b64e(salt)}${_b64e(dk)}"


def verify_password(password: str, stored: str) -> bool:
    """Verify a password against a stored PBKDF2 hash."""
    try:
        scheme, iters_s, salt_s, hash_s = stored.split("$", 3)
        if scheme != "pbkdf2_sha256":
            return False
        iterations = int(iters_s)
        salt = _b64d(salt_s)
        expected = _b64d(hash_s)
        dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
        return hmac.compare_digest(dk, expected)
    except Exception:
        return False


def generate_password(length: int = 20) -> str:
    alphabet = "abcdefghijkmnopqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no confusing chars
    return "".join(secrets.choice(alphabet) for _ in range(length))


def ensure_admin_credentials() -> Tuple[bool, str]:
    """Ensure admin password + session secret exist.

    Returns:
      (created_new_password, plaintext_password_if_created_else_empty)
    """
    s = load_settings()
    changed = False

    # Session secret (used for cookie session signing)
    if not s.get("session_secret"):
        s["session_secret"] = secrets.token_urlsafe(32)
        changed = True

    # Admin password
    created_pwd = False
    plain_pwd = ""

    if not s.get("admin_password_hash"):
        plain_pwd = generate_password()
        s["admin_password_hash"] = hash_password(plain_pwd)
        created_pwd = True
        changed = True

        # Write plaintext password to file (installer can read once)
        try:
            path = Path(ADMIN_PASSWORD_FILE)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(plain_pwd + "\n", encoding="utf-8")
            try:
                path.chmod(0o600)
            except Exception:
                pass
        except Exception as e:
            logger.warning("Failed to write admin password file: %s", e)

        logger.warning(
            "Admin password was generated because none existed. "
            "Read it from %s",
            str(ADMIN_PASSWORD_FILE),
        )

    if changed:
        save_settings(s)

    return created_pwd, plain_pwd
