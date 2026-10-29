import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models import Business, BusinessStatus, User, UserRole
from tests.integration.conftest import BUYER_PAYLOAD, register_buyer, register_seller

pytestmark = pytest.mark.integration


async def test_buyer_registration_creates_a_buyer(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    response = await register_buyer(api_client)

    assert response.status_code == 201
    body = response.json()
    assert body["role"] == UserRole.BUYER
    assert body["status"] == "active"
    assert body["email_verified_at"] is None

    stored = await session.execute(select(User).where(User.email == "buyer@example.com"))
    user = stored.scalar_one()
    assert user.role is UserRole.BUYER


async def test_registration_lowercases_the_email(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    """Buyer@Example.com and buyer@example.com must not become two accounts."""
    await register_buyer(api_client)

    response = await register_buyer(api_client, email="BUYER@example.com")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "conflict"


async def test_registration_sets_all_auth_cookies(api_client: AsyncClient) -> None:
    settings = get_settings()

    await register_buyer(api_client)

    assert api_client.cookies[settings.access_cookie]
    assert api_client.cookies[settings.refresh_cookie]
    assert api_client.cookies[settings.csrf_cookie]


async def test_duplicate_email_returns_conflict_not_server_error(api_client: AsyncClient) -> None:
    await register_buyer(api_client)

    response = await register_buyer(api_client, phone="+37411111111")

    assert response.status_code == 409


async def test_duplicate_phone_returns_conflict(api_client: AsyncClient) -> None:
    await register_buyer(api_client, phone="+37422222222")

    response = await register_buyer(api_client, email="other@example.com", phone="+37422222222")

    assert response.status_code == 409


async def test_short_password_is_rejected_by_the_backend(api_client: AsyncClient) -> None:
    response = await register_buyer(api_client, password="short")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_failed"


async def test_invalid_email_is_rejected(api_client: AsyncClient) -> None:
    response = await register_buyer(api_client, email="not-an-email")

    assert response.status_code == 422


async def test_password_is_never_echoed_back(api_client: AsyncClient) -> None:
    response = await register_buyer(api_client)

    assert BUYER_PAYLOAD["password"] not in response.text


async def test_seller_registration_creates_a_pending_business(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    response = await register_seller(api_client)

    assert response.status_code == 201
    body = response.json()
    assert body["user"]["role"] == UserRole.SELLER
    assert body["business"]["status"] == BusinessStatus.PENDING

    stored = await session.execute(select(Business))
    assert stored.scalar_one().legal_name == 'ИП "Тестовый"'


async def test_seller_registration_requires_legal_name(api_client: AsyncClient) -> None:
    payload = {
        "email": "nolegal@example.com",
        "password": "seller-password-1",
        "display_name": "Магазин",
    }

    response = await api_client.post("/api/v1/auth/register/seller", json=payload)

    assert response.status_code == 422
