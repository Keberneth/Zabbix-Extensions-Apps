"""Encryption helpers for storing secrets (API keys) at rest.

We use Fernet symmetric encryption from the `cryptography` package.

Security note:
- The encryption key is stored locally on disk (default: /etc/network-map/secret.key).
- This protects against accidental exposure of the settings file, but anyone with root
  access (or access to the key file) can decrypt the secrets.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken

from config import SECRET_KEY_FILE, SETTINGS_DIR


def _ensure_parent_dir(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def get_or_create_key(path: Path = SECRET_KEY_FILE) -> bytes:
    """Return the Fernet key, generating it if it doesn't exist."""
    path = Path(path)
    _ensure_parent_dir(path)

    if path.exists():
        data = path.read_bytes().strip()
        if data:
            return data

    key = Fernet.generate_key()

    # Write with restrictive permissions.
    # We can't reliably `chmod` on all platforms, but in Linux it works.
    path.write_bytes(key)
    try:
        path.chmod(0o600)
    except Exception:
        pass

    # Make sure settings dir also has sane permissions.
    try:
        Path(SETTINGS_DIR).mkdir(parents=True, exist_ok=True)
        Path(SETTINGS_DIR).chmod(0o700)
    except Exception:
        pass

    return key


def get_fernet() -> Fernet:
    return Fernet(get_or_create_key())


def encrypt_str(value: str) -> str:
    """Encrypt a string value to a urlsafe base64 token."""
    if value is None:
        return ""
    value = str(value)
    if value == "":
        return ""
    token = get_fernet().encrypt(value.encode("utf-8"))
    return token.decode("utf-8")


def decrypt_str(token: str) -> str:
    """Decrypt an encrypted token back to plaintext.

    Returns an empty string on missing/invalid tokens.
    """
    if not token:
        return ""
    try:
        plain = get_fernet().decrypt(str(token).encode("utf-8"))
        return plain.decode("utf-8")
    except (InvalidToken, ValueError, TypeError):
        return ""
