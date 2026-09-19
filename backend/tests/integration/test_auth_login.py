import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models import RefreshToken, User, UserStatus
from tests.integration.conftest import BUYER_PAYLOAD, csrf_headers, login, register_buyer

pytestmark = pytest.mark.integration

EMAIL = "buyer@example.com"
PASSWORD = str(BUYER_PAYLOAD["password"])


async def test_login_succeeds_with_correct_password(api_client: AsyncClient) -> None:
    await register_buyer(api_client)
    api_client.cookies.clear()

    response = await login(api_client, EMAIL, PASSWORD)

    assert response.status_code == 200
    assert response.json()["email"] == EMAIL
    assert api_client.cookies[get_settings().access_cookie_name]


async def test_login_is_case_insensitive_in_email(api_client: AsyncClient) -> None:
    await register_buyer(api_client)

    response = await login(api_client, "BUYER@EXAMPLE.COM", PASSWORD)

    assert response.status_code == 200


async def test_wrong_password_and_unknown_email_are_indistinguishable(
    api_client: AsyncClient,
) -> None:
    """A different answer for an unknown address would turn login into an account directory."""
    await register_buyer(api_client)

    wrong_password = await login(api_client, EMAIL, "definitely-wrong-1")
    unknown_email = await login(api_client, "nobody@example.com", PASSWORD)

    assert wrong_password.status_code == unknown_email.status_code == 401
    assert wrong_password.json() == unknown_email.json()


async def test_blocked_account_cannot_log_in(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    await register_buyer(api_client)
    user = (await session.execute(select(User).where(User.email == EMAIL))).scalar_one()
    user.status = UserStatus.BLOCKED
    await session.flush()

    response = await login(api_client, EMAIL, PASSWORD)

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "account_not_active"


async def test_logout_revokes_the_refresh_token(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    await register_buyer(api_client)

    response = await api_client.post("/api/v1/auth/logout", headers=csrf_headers(api_client))

    assert response.status_code == 204
    tokens = (await session.execute(select(RefreshToken))).scalars().all()
    assert all(token.revoked_at is not None for token in tokens)


async def test_logout_clears_cookies(api_client: AsyncClient) -> None:
    settings = get_settings()
    await register_buyer(api_client)

    await api_client.post("/api/v1/auth/logout", headers=csrf_headers(api_client))

    assert settings.access_cookie_name not in api_client.cookies
    assert settings.refresh_cookie_name not in api_client.cookies


async def test_logout_without_csrf_header_is_refused(api_client: AsyncClient) -> None:
    await register_buyer(api_client)

    response = await api_client.post("/api/v1/auth/logout")

    assert response.status_code == 403
