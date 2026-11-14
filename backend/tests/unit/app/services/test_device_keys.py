"""Proving that the browser still holds the key it registered.

A session cookie is a bearer token: whoever has a copy is the account. A device key narrows
that — the browser generates a key pair it cannot export, registers the public half, and signs
a short statement when it wants its session renewed. Copying the cookie no longer copies the
ability to keep it alive.

Renewal is the moment worth binding, so the statement covers the method and the full address
as well as the time: a signature captured from one call cannot be presented on another.

Replay is stopped by time rather than by a list. Each proof must be newer than the last one
this session accepted, so a captured signature is worth only the seconds before the honest
client sends its next one — and if the attacker wins that race, the honest client's own token
comes back as a replay, which revokes the family. The theft ends either way.
"""

import base64
import json
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec

from app.models import Session
from app.services import device_keys

METHOD = "POST"
URL = "https://api.allstore.am/api/v1/auth/refresh"


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _key(curve: ec.EllipticCurve | None = None) -> ec.EllipticCurvePrivateKey:
    return ec.generate_private_key(curve or ec.SECP256R1())


def _public(key: ec.EllipticCurvePrivateKey) -> str:
    return _b64(
        key.public_key().public_bytes(
            serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
        )
    )


def _proof(
    key: ec.EllipticCurvePrivateKey,
    *,
    method: str = METHOD,
    url: str = URL,
    issued_at: datetime | None = None,
    claims: dict[str, Any] | None = None,
) -> str:
    moment = issued_at or datetime.now(UTC)
    body = (
        claims
        if claims is not None
        else {
            "htm": method,
            "htu": url,
            "iat": int(moment.timestamp()),
        }
    )
    payload = _b64(json.dumps(body).encode())
    signature = key.sign(payload.encode(), ec.ECDSA(hashes.SHA256()))
    return f"{payload}.{_b64(signature)}"


def _session(key: ec.EllipticCurvePrivateKey | None = None, **overrides: Any) -> Session:
    row = Session(device_public_key=None if key is None else _public(key), last_proof_at=None)
    for name, value in overrides.items():
        setattr(row, name, value)
    return row


def test_a_browser_that_holds_the_key_is_believed() -> None:
    key = _key()
    moment = datetime.now(UTC)

    issued = device_keys.verify(
        _session(key), _proof(key, issued_at=moment), method=METHOD, url=URL
    )

    assert int(issued.timestamp()) == int(moment.timestamp())


def test_a_session_with_no_key_cannot_be_proved() -> None:
    """A device that could not hold one is allowed a session; it is not allowed this."""
    with pytest.raises(device_keys.DeviceProofError):
        device_keys.verify(_session(), _proof(_key()), method=METHOD, url=URL)


def test_a_missing_proof_is_a_refusal_rather_than_a_pass() -> None:
    key = _key()

    with pytest.raises(device_keys.DeviceProofError):
        device_keys.verify(_session(key), None, method=METHOD, url=URL)


def test_somebody_else_s_signature_is_refused() -> None:
    """The whole point: holding the cookie is not holding the key."""
    with pytest.raises(device_keys.DeviceProofError, match="не совпадает"):
        device_keys.verify(_session(_key()), _proof(_key()), method=METHOD, url=URL)


@pytest.mark.parametrize(
    "header",
    [
        "nodot",
        "a.b.c",
        "не-base64!.подпись",
        f"{_b64(b'not json')}.signature",
        f"{_b64(json.dumps(['a list']).encode())}.signature",
    ],
)
def test_a_proof_nobody_could_read_is_refused(header: str) -> None:
    with pytest.raises(device_keys.DeviceProofError, match="нечитаема"):
        device_keys.verify(_session(_key()), header, method=METHOD, url=URL)


def test_a_signature_captured_from_another_call_is_refused() -> None:
    key = _key()
    elsewhere = _proof(key, url="https://api.allstore.am/api/v1/products")

    with pytest.raises(device_keys.DeviceProofError, match="не для этого запроса"):
        device_keys.verify(_session(key), elsewhere, method=METHOD, url=URL)


def test_a_signature_made_for_another_method_is_refused() -> None:
    key = _key()

    with pytest.raises(device_keys.DeviceProofError, match="не для этого запроса"):
        device_keys.verify(_session(key), _proof(key, method="GET"), method=METHOD, url=URL)


@pytest.mark.parametrize("skew", [timedelta(minutes=3), timedelta(minutes=-3)])
def test_a_clock_too_far_out_of_step_is_not_believed(skew: timedelta) -> None:
    """Both ways: a proof from the future is as suspect as one from an hour ago."""
    key = _key()
    proof = _proof(key, issued_at=datetime.now(UTC) + skew)

    with pytest.raises(device_keys.DeviceProofError, match="просрочена"):
        device_keys.verify(_session(key), proof, method=METHOD, url=URL)


def test_a_clock_a_little_out_of_step_still_is() -> None:
    """Telephones drift, and a visitor whose clock is a minute off is not an attacker."""
    key = _key()
    proof = _proof(key, issued_at=datetime.now(UTC) - timedelta(minutes=1))

    assert device_keys.verify(_session(key), proof, method=METHOD, url=URL) is not None


def test_a_proof_already_seen_is_refused() -> None:
    key = _key()
    moment = datetime.now(UTC)
    row = _session(key, last_proof_at=moment)

    with pytest.raises(device_keys.DeviceProofError, match="уже использована"):
        device_keys.verify(row, _proof(key, issued_at=moment), method=METHOD, url=URL)


def test_an_older_proof_than_the_last_one_is_refused_too() -> None:
    """Not merely the same one: a captured signature is worth nothing the moment the honest
    client has sent a newer one."""
    key = _key()
    now = datetime.now(UTC)
    row = _session(key, last_proof_at=now)

    with pytest.raises(device_keys.DeviceProofError, match="уже использована"):
        device_keys.verify(
            row, _proof(key, issued_at=now - timedelta(seconds=30)), method=METHOD, url=URL
        )


@pytest.mark.parametrize("iat", [None, "1762000000", 1.5, 10**20])
def test_a_proof_with_no_usable_time_is_refused(iat: Any) -> None:
    key = _key()
    claims: dict[str, Any] = {"htm": METHOD, "htu": URL}
    if iat is not None:
        claims["iat"] = iat

    with pytest.raises(device_keys.DeviceProofError):
        device_keys.verify(_session(key), _proof(key, claims=claims), method=METHOD, url=URL)


def test_only_one_curve_is_accepted() -> None:
    """A list of curves to support is a list of curves to get wrong, and every browser that
    can do this at all can do P-256."""
    assert device_keys.load_public_key(_public(_key())) is not None

    with pytest.raises(device_keys.DeviceKeyError, match="не того типа"):
        device_keys.load_public_key(_public(_key(ec.SECP384R1())))


@pytest.mark.parametrize("encoded", ["не ключ", "", _b64(b"not a key at all")])
def test_a_key_nobody_could_read_is_refused(encoded: str) -> None:
    with pytest.raises(device_keys.DeviceKeyError, match="нечитаем"):
        device_keys.load_public_key(encoded)
