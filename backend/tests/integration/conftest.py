import uuid
from typing import Any

from httpx import AsyncClient, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import hash_password
from app.models import Category, User, UserRole

PRODUCTS_URL = "/api/v1/products"
CONTACTS_URL = "/api/v1/stores/me/contacts"

BUYER_PAYLOAD = {"email": "Buyer@Example.com", "password": "buyer-password-1"}
SELLER_PAYLOAD = {
    "email": "seller@example.com",
    "password": "seller-password-1",
    "legal_name": 'ИП "Тестовый"',
    "display_name": "Тестовый магазин",
}


def csrf_headers(client: AsyncClient) -> dict[str, str]:
    settings = get_settings()
    return {settings.csrf_header_name: client.cookies[settings.csrf_cookie_name]}


async def register_buyer(client: AsyncClient, **overrides: Any) -> Response:
    return await client.post("/api/v1/auth/register/buyer", json={**BUYER_PAYLOAD, **overrides})


async def register_seller(client: AsyncClient, **overrides: Any) -> Response:
    return await client.post("/api/v1/auth/register/seller", json={**SELLER_PAYLOAD, **overrides})


async def login(client: AsyncClient, email: str, password: str) -> Response:
    return await client.post("/api/v1/auth/login", json={"email": email, "password": password})


async def become_moderator(client: AsyncClient, session: AsyncSession) -> User:
    """There is no self-registration for moderators, so the account is seeded and then logged in."""
    password = "moderator-password-1"
    user = User(
        email=f"moderator-{uuid.uuid4().hex}@example.com",
        password_hash=hash_password(password),
        role=UserRole.MODERATOR,
    )
    session.add(user)
    await session.flush()
    client.cookies.clear()
    await login(client, user.email, password)
    return user


async def register_second_seller(client: AsyncClient) -> None:
    """A seller registration replaces the cookies, so the client acts as the new account."""
    client.cookies.clear()
    await register_seller(client, email=f"seller-{uuid.uuid4().hex}@example.com")


async def seeded_category(session: AsyncSession, slug: str = "electronics") -> Category:
    """The starting catalogue comes from migration 0004, committed outside the test transaction."""
    result = await session.execute(select(Category).where(Category.slug == slug))
    return result.scalar_one()


def product_payload(category_id: uuid.UUID, **overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "category_id": str(category_id),
        "name": "Кружка керамическая",
        "price": "1500.00",
    }
    body.update(overrides)
    return body


async def set_contacts(client: AsyncClient, *items: dict[str, str]) -> Response:
    payload = list(items) or [{"platform": "phone", "value": "+37410123456"}]
    return await client.put(CONTACTS_URL, json={"items": payload}, headers=csrf_headers(client))


async def create_product(client: AsyncClient, category_id: uuid.UUID, **overrides: Any) -> Response:
    """Seeds a contact first: since этап 11 a product may not enter the queue without one,
    so a seller who can sell is a seller a buyer can reach. The rule itself is tested in
    test_contacts.py, where the seeding is deliberately skipped."""
    await set_contacts(client)
    return await client.post(
        PRODUCTS_URL, json=product_payload(category_id, **overrides), headers=csrf_headers(client)
    )
