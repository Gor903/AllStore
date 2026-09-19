import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User, UserRole
from tests.integration.conftest import register_buyer, register_seller

pytestmark = pytest.mark.integration


async def test_buyer_cannot_reach_a_seller_endpoint(api_client: AsyncClient) -> None:
    await register_buyer(api_client)

    response = await api_client.get("/api/v1/users/me/business")

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "permission_denied"


async def test_buyer_cannot_reach_an_admin_endpoint(api_client: AsyncClient) -> None:
    await register_buyer(api_client)

    response = await api_client.get(f"/api/v1/admin/users/{uuid.uuid4()}")

    assert response.status_code == 403


async def test_seller_cannot_reach_an_admin_endpoint(api_client: AsyncClient) -> None:
    await register_seller(api_client)

    response = await api_client.get(f"/api/v1/admin/users/{uuid.uuid4()}")

    assert response.status_code == 403


async def test_anonymous_request_to_a_role_endpoint_is_unauthenticated_not_forbidden(
    api_client: AsyncClient,
) -> None:
    response = await api_client.get("/api/v1/users/me/business")

    assert response.status_code == 401


async def test_seller_sees_own_business(api_client: AsyncClient) -> None:
    await register_seller(api_client)

    response = await api_client.get("/api/v1/users/me/business")

    assert response.status_code == 200
    assert response.json()["display_name"] == "Тестовый магазин"


async def test_admin_can_read_any_user(api_client: AsyncClient, session: AsyncSession) -> None:
    """The role is read from the database, not from the token — a promotion needs no re-login."""
    await register_buyer(api_client, email="target@example.com")
    target = (await session.execute(select(User))).scalars().one()
    api_client.cookies.clear()
    await register_seller(api_client, email="admin@example.com")
    admin = (
        await session.execute(select(User).where(User.email == "admin@example.com"))
    ).scalar_one()
    admin.role = UserRole.ADMIN
    await session.flush()

    response = await api_client.get(f"/api/v1/admin/users/{target.id}")

    assert response.status_code == 200
    assert response.json()["email"] == "target@example.com"


async def test_admin_gets_404_for_a_missing_user(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    await register_buyer(api_client, email="admin@example.com")
    user = (await session.execute(select(User))).scalars().one()
    user.role = UserRole.ADMIN
    await session.flush()

    response = await api_client.get(f"/api/v1/admin/users/{uuid.uuid4()}")

    assert response.status_code == 404
