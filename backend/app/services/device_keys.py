"""Proving that the browser still holds the key it registered.

A session cookie is a bearer token: whoever has a copy is the account. That is the whole of
what cross-site scripting and a stolen laptop are worth. A device key narrows it — the browser
generates a key pair it cannot itself export, registers the public half, and signs a short
statement when it wants its session renewed. Copying the cookie no longer copies the ability
to keep it alive.

What this does not do, and must not be mistaken for: it is no defence against a script running
on our own page. That script cannot read the private key either, but it can ask the browser to
sign with it, which is all it needs. The answer to that is the content security policy from
stage 2; this is the answer to a cookie that has already left the building.

Signing every request was considered and refused — expensive, and a signature on a request for
a product photograph protects nothing. Renewal is the moment worth binding: it is where a
session's life is extended, so an attacker who cannot renew holds something with an end date.

Replay is stopped by time rather than by a list. Each proof must be newer than the last one
this session accepted, so a captured signature is worth only the seconds before the honest
client sends its next one — and if the attacker does win that race, the honest client's token
stops working and comes back as a replay, which revokes the family. The theft ends either way.
"""

import base64
import binascii
import json
from datetime import UTC, datetime, timedelta
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from sqlalchemy.ext.asyncio import AsyncSession as DbSession

from app.core.errors import PermissionDeniedError
from app.models import Session

# How far out of step with us a device's clock may be and still be believed.
PROOF_FRESHNESS = timedelta(minutes=2)
HEADER = "X-Device-Proof"


class DeviceProofError(PermissionDeniedError):
    code = "device_proof_invalid"


class DeviceKeyError(PermissionDeniedError):
    code = "device_key_invalid"


def _unpad(value: str) -> bytes:
    """base64url without padding, which is how a browser's `btoa` dance usually ends up."""
    try:
        return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    except (binascii.Error, ValueError) as exc:
        raise DeviceProofError("Подпись устройства нечитаема") from exc


def load_public_key(encoded: str) -> ec.EllipticCurvePublicKey:
    """A public key as the browser exports it: SPKI, base64.

    Only P-256 is accepted. A list of curves to support is a list of curves to get wrong, and
    every browser that can do this at all can do this one.
    """
    try:
        key = serialization.load_der_public_key(_unpad(encoded))
    except (ValueError, DeviceProofError) as exc:
        raise DeviceKeyError("Ключ устройства нечитаем") from exc
    if not isinstance(key, ec.EllipticCurvePublicKey) or not isinstance(key.curve, ec.SECP256R1):
        raise DeviceKeyError("Ключ устройства не того типа")
    return key


def _parse(header: str) -> tuple[dict[str, Any], bytes, bytes]:
    parts = header.split(".")
    if len(parts) != 2:
        raise DeviceProofError("Подпись устройства нечитаема")
    payload_raw, signature_raw = parts
    try:
        claims = json.loads(_unpad(payload_raw))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise DeviceProofError("Подпись устройства нечитаема") from exc
    if not isinstance(claims, dict):
        raise DeviceProofError("Подпись устройства нечитаема")
    return claims, payload_raw.encode(), _unpad(signature_raw)


def verify(row: Session, header: str | None, *, method: str, url: str) -> datetime:
    """Returns when the proof says it was made, having checked that it says the truth.

    The statement covers the method and the address as well as the time, so a signature
    captured from one call cannot be presented on another.
    """
    if row.device_public_key is None:
        raise DeviceProofError("К этой сессии не привязан ключ устройства")
    if not header:
        raise DeviceProofError("Отсутствует подпись устройства")

    claims, signed, signature = _parse(header)
    key = load_public_key(row.device_public_key)
    try:
        key.verify(signature, signed, ec.ECDSA(hashes.SHA256()))
    except InvalidSignature as exc:
        raise DeviceProofError("Подпись устройства не совпадает") from exc

    if claims.get("htm") != method or claims.get("htu") != url:
        raise DeviceProofError("Подпись устройства выдана не для этого запроса")

    issued_at = _issued_at(claims)
    now = datetime.now(UTC)
    if abs(now - issued_at) > PROOF_FRESHNESS:
        raise DeviceProofError("Подпись устройства просрочена")
    if row.last_proof_at is not None and issued_at <= row.last_proof_at:
        # not newer than one we have already accepted, so it is one we have already seen
        raise DeviceProofError("Подпись устройства уже использована")
    return issued_at


def _issued_at(claims: dict[str, Any]) -> datetime:
    raw = claims.get("iat")
    if not isinstance(raw, int):
        raise DeviceProofError("Подпись устройства без времени")
    try:
        return datetime.fromtimestamp(raw, tz=UTC)
    except (OverflowError, OSError, ValueError) as exc:
        raise DeviceProofError("Подпись устройства без времени") from exc


async def remember(db: DbSession, row: Session, issued_at: datetime) -> None:
    row.last_proof_at = issued_at
    await db.flush()


async def bind(db: DbSession, row: Session, encoded_key: str) -> bool:
    """Attaches a key to this session. Says whether anything changed.

    Offering the key that is already there is not an error: the browser has no way of knowing
    whether this session was bound before it reloaded the page, so asking again is the
    ordinary case rather than a mistake worth refusing.

    Offering a *different* one is refused. The whole point of the key is that only this
    browser holds it, and a session that could swap it would hand anybody with the cookie a
    way to become the device.
    """
    load_public_key(encoded_key)
    if row.device_public_key == encoded_key:
        return False
    if row.device_public_key is not None:
        raise DeviceKeyError("К этой сессии уже привязан другой ключ устройства")
    row.device_public_key = encoded_key
    await db.flush()
    return True
