"""Encrypting the few values that have to be stored readable but must not be readable.

A password is hashed: nothing ever needs the original back. A TOTP secret is different — the
server has to compute codes from it, so it has to be recoverable, and "recoverable" and
"plain in the table" are not the same thing. A database dump, a backup on somebody's laptop,
a read-only replica somebody was given access to: each of those is a copy of every second
factor on the platform unless the column is encrypted.

AES-GCM, so a modified ciphertext is a failure rather than a different secret, with the key
derived from `SECRET_KEY`. This is not key management — rotating `SECRET_KEY` makes every
stored value unreadable, and the people it belongs to would have to enrol again. That is the
honest cost of having one secret instead of a key service, and it is written here so nobody
discovers it during a rotation.
"""

import base64
import hashlib
import secrets

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import Settings

# 96 bits, which is what GCM is specified for; anything else makes the library derive one
NONCE_BYTES = 12
# A label, so the key used here cannot be the key used by anything else that one day derives
# from the same secret. Changing it is the same as rotating: everything stored becomes unreadable.
PURPOSE = b"allstore/totp-secret/v1"


def _key(settings: Settings) -> bytes:
    return hashlib.pbkdf2_hmac(
        "sha256", settings.secret_key.get_secret_value().encode(), PURPOSE, 100_000, dklen=32
    )


def lock(settings: Settings, plaintext: str) -> str:
    """Nonce and ciphertext together, base64url, because this goes in a text column."""
    nonce = secrets.token_bytes(NONCE_BYTES)
    sealed = AESGCM(_key(settings)).encrypt(nonce, plaintext.encode(), None)
    return base64.urlsafe_b64encode(nonce + sealed).decode()


def unlock(settings: Settings, stored: str) -> str | None:
    """The value back, or nothing when it cannot be had.

    Nothing means the key changed or the row was tampered with. Both are the same answer to
    the caller — this account's second factor cannot be used and has to be set up again.
    """
    try:
        raw = base64.urlsafe_b64decode(stored)
        return AESGCM(_key(settings)).decrypt(raw[:NONCE_BYTES], raw[NONCE_BYTES:], None).decode()
    except (InvalidTag, ValueError):
        return None
