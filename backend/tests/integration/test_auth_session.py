from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models import RefreshToken, User, UserStatus
from tests.integration.conftest import csrf_headers, register_buyer

pytestmark = pytest.mark.integration


async def test_me_requires_authentication(api_client: AsyncClient) -> None:
    response = await api_client.get("/api/v1/users/me")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "authentication_failed"


async def test_me_returns_the_logged_in_user(api_client: AsyncClient) -> None:
    await register_buyer(api_client)

    response = await api_client.get("/api/v1/users/me")

    assert response.status_code == 200
    assert response.json()["email"] == "buyer@example.com"


async def test_tampered_access_token_is_rejected(api_client: AsyncClient) -> None:
    settings = get_settings()
    await register_buyer(api_client)
    api_client.cookies.set(settings.access_cookie_name, "not.a.jwt")

    response = await api_client.get("/api/v1/users/me")

    assert response.status_code == 401


async def test_blocking_an_account_takes_effect_before_the_token_expires(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    """The token stays cryptographically valid, so the status is what must stop the request."""
    await register_buyer(api_client)
    user = (await session.execute(select(User))).scalars().first()
    assert user is not None
    user.status = UserStatus.BLOCKED
    await session.flush()

    response = await api_client.get("/api/v1/users/me")

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "account_not_active"


async def test_refresh_rotates_the_token(api_client: AsyncClient, session: AsyncSession) -> None:
    settings = get_settings()
    await register_buyer(api_client)
    first_refresh = api_client.cookies[settings.refresh_cookie_name]

    response = await api_client.post("/api/v1/auth/refresh", headers=csrf_headers(api_client))

    assert response.status_code == 200
    assert api_client.cookies[settings.refresh_cookie_name] != first_refresh
    tokens = (await session.execute(select(RefreshToken))).scalars().all()
    assert len(tokens) == 2
    rotated = next(token for token in tokens if token.revoked_at is not None)
    assert rotated.replaced_by_id is not None


async def test_replaying_a_rotated_token_kills_every_session(
    committing_api_client: AsyncClient, fresh_session: AsyncSession
) -> None:
    """Reuse of an already rotated token means it leaked — every session of that user dies.

    Read from outside the request on purpose. The refusal was never in doubt; what matters is
    that the revocation it triggers is still there afterwards, and a session that took part in
    the request would report a write that never reached the database.
    """
    settings = get_settings()
    client = committing_api_client
    await register_buyer(client)
    stolen = client.cookies[settings.refresh_cookie_name]
    await client.post("/api/v1/auth/refresh", headers=csrf_headers(client))
    client.cookies.set(settings.refresh_cookie_name, stolen)

    response = await client.post("/api/v1/auth/refresh", headers=csrf_headers(client))

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_refresh_token"
    tokens = (await fresh_session.execute(select(RefreshToken))).scalars().all()
    # without this the assertion below passes on an empty set and proves nothing
    assert len(tokens) == 2
    assert all(token.revoked_at is not None for token in tokens)


async def test_refresh_without_csrf_header_is_refused(api_client: AsyncClient) -> None:
    await register_buyer(api_client)

    response = await api_client.post("/api/v1/auth/refresh")

    assert response.status_code == 403


async def test_refresh_with_mismatched_csrf_header_is_refused(api_client: AsyncClient) -> None:
    settings = get_settings()
    await register_buyer(api_client)

    response = await api_client.post(
        "/api/v1/auth/refresh", headers={settings.csrf_header_name: "someone-elses-token"}
    )

    assert response.status_code == 403


async def test_refresh_after_logout_is_refused(api_client: AsyncClient) -> None:
    await register_buyer(api_client)
    headers = csrf_headers(api_client)
    settings = get_settings()
    refresh_cookie = api_client.cookies[settings.refresh_cookie_name]
    await api_client.post("/api/v1/auth/logout", headers=headers)
    api_client.cookies.set(settings.refresh_cookie_name, refresh_cookie)
    api_client.cookies.set(settings.csrf_cookie_name, headers[settings.csrf_header_name])

    response = await api_client.post("/api/v1/auth/refresh", headers=headers)

    assert response.status_code == 401


async def test_refresh_without_a_cookie_is_refused(api_client: AsyncClient) -> None:
    settings = get_settings()
    await register_buyer(api_client)
    headers = csrf_headers(api_client)
    api_client.cookies.delete(settings.refresh_cookie_name)

    response = await api_client.post("/api/v1/auth/refresh", headers=headers)

    assert response.status_code == 401


async def test_refresh_with_an_unknown_token_is_refused(api_client: AsyncClient) -> None:
    settings = get_settings()
    await register_buyer(api_client)
    api_client.cookies.set(settings.refresh_cookie_name, "token-that-was-never-issued")

    response = await api_client.post("/api/v1/auth/refresh", headers=csrf_headers(api_client))

    assert response.status_code == 401


async def test_expired_refresh_token_is_refused(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    await register_buyer(api_client)
    stored = (await session.execute(select(RefreshToken))).scalar_one()
    stored.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    await session.flush()

    response = await api_client.post("/api/v1/auth/refresh", headers=csrf_headers(api_client))

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_refresh_token"


async def test_refresh_is_refused_after_the_account_is_deleted(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    """The token outlives the row only in this window; the service must not hand out a session."""
    await register_buyer(api_client)
    headers = csrf_headers(api_client)
    stored = (await session.execute(select(RefreshToken))).scalar_one()
    await session.execute(text("DELETE FROM users WHERE id = :id"), {"id": stored.user_id})
    await session.flush()

    response = await api_client.post("/api/v1/auth/refresh", headers=headers)

    assert response.status_code == 401
