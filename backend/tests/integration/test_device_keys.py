"""A session that can prove it is still the same browser.

The cookie is a bearer token: a copy of it is the account. Binding narrows that — the browser
holds a key it cannot export, and renewal needs a signature. An attacker who took the cookie
holds something that expires and cannot be kept alive.

Everything here signs for real. A test that mocked the signature would be checking that the
code calls a function, which is not the thing worth knowing.
"""

import base64
import json
import time
from datetime import UTC, datetime, timedelta

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Session
from app.services.device_keys import HEADER
from tests.integration.conftest import csrf_headers, register_buyer

pytestmark = pytest.mark.integration

DEVICE_KEY = "/api/v1/auth/sessions/device-key"
RENEW = "/api/v1/auth/renew"
RENEW_URL = f"http://test{RENEW}"


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _a_device() -> tuple[ec.EllipticCurvePrivateKey, str]:
    private = ec.generate_private_key(ec.SECP256R1())
    public = private.public_key().public_bytes(
        serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    return private, _b64(public)


def _proof(
    private: ec.EllipticCurvePrivateKey,
    *,
    method: str = "POST",
    url: str = RENEW_URL,
    issued_at: int | None = None,
) -> str:
    claims = {"htm": method, "htu": url, "iat": issued_at or int(time.time())}
    payload = _b64(json.dumps(claims).encode())
    signature = private.sign(payload.encode(), ec.ECDSA(hashes.SHA256()))
    return f"{payload}.{_b64(signature)}"


async def _bind(client: AsyncClient, public_key: str) -> int:
    response = await client.post(
        DEVICE_KEY, json={"public_key": public_key}, headers=csrf_headers(client)
    )
    return response.status_code


async def test_offering_the_same_key_again_is_not_an_error(api_client: AsyncClient) -> None:
    """A browser cannot tell whether this session was bound before the page reloaded, so
    asking again is the ordinary case."""
    _, public_key = _a_device()
    await register_buyer(api_client)

    assert await _bind(api_client, public_key) == 204
    assert await _bind(api_client, public_key) == 204


async def test_the_key_cannot_be_swapped_for_another(api_client: AsyncClient) -> None:
    """Swapping it would hand anybody with the cookie a way to become the device."""
    _, public_key = _a_device()
    _, another = _a_device()
    await register_buyer(api_client)
    await _bind(api_client, public_key)

    assert await _bind(api_client, another) == 403


async def test_nonsense_is_not_a_key(api_client: AsyncClient) -> None:
    await register_buyer(api_client)

    response = await api_client.post(
        DEVICE_KEY, json={"public_key": "not-a-key-at-all"}, headers=csrf_headers(api_client)
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "device_key_invalid"


async def test_binding_buys_the_session_a_longer_life(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    _, public_key = _a_device()
    await register_buyer(api_client)
    before = (await session.execute(select(Session))).scalar_one().absolute_expires_at

    await _bind(api_client, public_key)

    session.expire_all()
    after = (await session.execute(select(Session))).scalar_one().absolute_expires_at
    assert after > before


async def test_a_bound_session_renews_with_its_signature(api_client: AsyncClient) -> None:
    private, public_key = _a_device()
    await register_buyer(api_client)
    await _bind(api_client, public_key)

    response = await api_client.post(
        RENEW, headers={**csrf_headers(api_client), HEADER: _proof(private)}
    )

    assert response.status_code == 200


async def test_a_bound_session_will_not_renew_without_one(api_client: AsyncClient) -> None:
    """The cookie alone used to be enough. That is the whole of what binding changes."""
    _, public_key = _a_device()
    await register_buyer(api_client)
    await _bind(api_client, public_key)

    response = await api_client.post(RENEW, headers=csrf_headers(api_client))

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "device_proof_invalid"


async def test_somebody_elses_signature_does_not_count(api_client: AsyncClient) -> None:
    _, public_key = _a_device()
    stranger, _ = _a_device()
    await register_buyer(api_client)
    await _bind(api_client, public_key)

    response = await api_client.post(
        RENEW, headers={**csrf_headers(api_client), HEADER: _proof(stranger)}
    )

    assert response.status_code == 403


async def test_a_signature_made_for_another_request_does_not_travel(
    api_client: AsyncClient,
) -> None:
    """The statement covers the method and the address, so a proof captured from one call is
    worth nothing on another."""
    private, public_key = _a_device()
    await register_buyer(api_client)
    await _bind(api_client, public_key)

    response = await api_client.post(
        RENEW,
        headers={
            **csrf_headers(api_client),
            HEADER: _proof(private, url="http://test/api/v1/auth/logout"),
        },
    )

    assert response.status_code == 403


async def test_an_old_signature_is_not_accepted(api_client: AsyncClient) -> None:
    private, public_key = _a_device()
    await register_buyer(api_client)
    await _bind(api_client, public_key)
    long_ago = int((datetime.now(UTC) - timedelta(hours=1)).timestamp())

    response = await api_client.post(
        RENEW, headers={**csrf_headers(api_client), HEADER: _proof(private, issued_at=long_ago)}
    )

    assert response.status_code == 403


async def test_the_same_signature_cannot_be_used_twice(api_client: AsyncClient) -> None:
    """Captured once, worth only the seconds before the honest client signs again."""
    private, public_key = _a_device()
    await register_buyer(api_client)
    await _bind(api_client, public_key)
    proof = _proof(private)

    first = await api_client.post(RENEW, headers={**csrf_headers(api_client), HEADER: proof})
    second = await api_client.post(RENEW, headers={**csrf_headers(api_client), HEADER: proof})

    assert first.status_code == 200
    assert second.status_code == 403
    assert second.json()["error"]["code"] == "device_proof_invalid"


async def test_a_bound_session_is_not_renewed_behind_the_clients_back(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    """Only the browser can sign, so the server stops renewing on its own once bound —
    otherwise the protection would be skipped by whatever request happened to come next."""
    _, public_key = _a_device()
    await register_buyer(api_client)
    await _bind(api_client, public_key)
    row = (await session.execute(select(Session))).scalar_one()
    row.created_at = datetime.now(UTC) - timedelta(days=1)
    await session.flush()

    assert (await api_client.get("/api/v1/users/me")).status_code == 200

    session.expire_all()
    rows = (await session.execute(select(Session))).scalars().all()
    assert len(rows) == 1, "the server renewed a session it cannot prove is still the device"


async def test_an_unbound_session_is_still_renewed_for_free(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    """A browser that cannot hold a key keeps the old protection: rotation it never asked for."""
    await register_buyer(api_client)
    row = (await session.execute(select(Session))).scalar_one()
    row.created_at = datetime.now(UTC) - timedelta(days=1)
    await session.flush()

    assert (await api_client.get("/api/v1/users/me")).status_code == 200

    session.expire_all()
    rows = (await session.execute(select(Session))).scalars().all()
    assert len(rows) == 2
