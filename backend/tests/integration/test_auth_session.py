import pytest
from httpx import AsyncClient
from sqlalchemy import select
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
    api_client: AsyncClient, session: AsyncSession
) -> None:
    """Reuse of an already rotated token means it leaked — every session of that user dies."""
    settings = get_settings()
    await register_buyer(api_client)
    stolen = api_client.cookies[settings.refresh_cookie_name]
    await api_client.post("/api/v1/auth/refresh", headers=csrf_headers(api_client))
    api_client.cookies.set(settings.refresh_cookie_name, stolen)

    response = await api_client.post("/api/v1/auth/refresh", headers=csrf_headers(api_client))

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_refresh_token"
    tokens = (await session.execute(select(RefreshToken))).scalars().all()
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
