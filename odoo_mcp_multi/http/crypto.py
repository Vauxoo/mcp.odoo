"""Encryption of stored Odoo credentials.

Users hand this server their own Odoo password or API key during the OAuth
consent step, so those secrets have to survive a restart. They are encrypted
with Fernet (AES-128-CBC + HMAC-SHA256) and the key lives in its own file,
separate from the database, so a stolen database backup is not enough to
recover them.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

__all__ = ["CredentialCipher", "InvalidToken", "load_or_create_key"]


def load_or_create_key(path: Path) -> bytes:
    """Return the Fernet key at ``path``, generating it on first use.

    The file is created with owner-only permissions; an existing file with
    looser permissions is tightened rather than rejected, since the common
    cause is a restore from backup.
    """
    path = Path(path)
    if path.exists():
        key = path.read_bytes().strip()
        if not key:
            raise ValueError(f"Secret key file '{path}' is empty. Delete it to generate a new one.")
        _harden(path)
        return key

    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    key = Fernet.generate_key()
    # Create with the right mode from the start — never world-readable, not
    # even for the instant between write and chmod.
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as fh:
        fh.write(key)
    return key


def _harden(path: Path) -> None:
    """Restrict a key file to owner read/write."""
    try:
        if (path.stat().st_mode & 0o077) != 0:
            path.chmod(0o600)
    except OSError:  # pragma: no cover - filesystems without POSIX modes
        pass


class CredentialCipher:
    """Encrypts and decrypts the JSON payloads kept in the auth store."""

    def __init__(self, key: bytes) -> None:
        self._fernet = Fernet(key)

    @classmethod
    def from_file(cls, path: Path) -> "CredentialCipher":
        return cls(load_or_create_key(path))

    def encrypt(self, payload: dict[str, Any]) -> bytes:
        """Serialize and encrypt a JSON-compatible mapping."""
        return self._fernet.encrypt(json.dumps(payload, default=str).encode("utf-8"))

    def decrypt(self, token: bytes) -> dict[str, Any]:
        """Decrypt and deserialize a payload produced by :meth:`encrypt`.

        Raises:
            InvalidToken: If the ciphertext was not produced by this key.
        """
        return json.loads(self._fernet.decrypt(token).decode("utf-8"))
