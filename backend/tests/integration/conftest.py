import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from httpx import AsyncClient, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import hash_password
from app.models import Category, User, UserRole

PRODUCTS_URL = "/api/v1/products"
CONTACTS_URL = "/api/v1/stores/me/contacts"
STORES_URL = "/api/v1/stores"
BUSINESS_MODERATION = "/api/v1/moderation/businesses"
PRODUCT_MODERATION = "/api/v1/moderation/products"

BUYER_PAYLOAD = {"email": "Buyer@Example.com", "password": "buyer-password-1"}
SELLER_PAYLOAD = {
    "email": "seller@example.com",
    "password": "seller-password-1",
    "legal_name": 'ИП "Тестовый"',
    "display_name": "Тестовый магазин",
}


def csrf_headers(client: AsyncClient) -> dict[str, str]:
    settings = get_settings()
    return {settings.csrf_header_name: client.cookies[settings.csrf_cookie]}


@dataclass(frozen=True)
class Registered:
    """What registration used to answer with, rebuilt after signing in.

    It no longer answers with the account: the same sentence comes back whether the address
    was free or taken, and no session is handed out, because either difference would let a
    caller tell the two apart. The suite still needs the identifiers, so the helper fetches
    them the way any client would — by asking who it is once it is in.
    """

    status_code: int
    body: dict[str, Any]

    def json(self) -> dict[str, Any]:
        return self.body


async def register_buyer(client: AsyncClient, **overrides: Any) -> Registered:
    """Registers and signs in, which is what every caller here wanted from the old 201."""
    payload = {**BUYER_PAYLOAD, **overrides}
    response = await client.post("/api/v1/auth/register/buyer", json=payload)
    if response.status_code != 202:
        return Registered(response.status_code, {})
    await login(client, str(payload["email"]), str(payload["password"]))
    me = await client.get("/api/v1/users/me")
    return Registered(response.status_code, dict(me.json()))


async def register_seller(
    client: AsyncClient, session: AsyncSession | None = None, **overrides: Any
) -> Registered:
    """The same, and — when given a session — with the address confirmed.

    Opening a shop needs a confirmed address, so a test that goes on to create one has to do
    what a real seller does first. The session is optional because plenty of tests register a
    seller only to check that something refuses them, and those never get that far.
    """
    payload = {**SELLER_PAYLOAD, **overrides}
    response = await client.post("/api/v1/auth/register/seller", json=payload)
    if response.status_code != 202:
        return Registered(response.status_code, {})
    await login(client, str(payload["email"]), str(payload["password"]))
    me = (await client.get("/api/v1/users/me")).json()
    if session is not None:
        await confirm_email(session, str(me["id"]))
    business = (await client.get("/api/v1/users/me/business")).json()
    return Registered(response.status_code, {"user": me, "business": business})


async def login(client: AsyncClient, email: str, password: str) -> Response:
    return await client.post("/api/v1/auth/login", json={"email": email, "password": password})


STAFF_PASSWORD = "staff-password-1"


async def seed_staff(session: AsyncSession, role: UserRole) -> User:
    """Moderators and administrators have no self-registration, so they are seeded.

    An administrator seeded here is the only one the platform may have: the unique partial
    index on the role sees to that, and a test that wants two is describing a platform this
    one is not.
    """
    user = User(
        email=f"{role}-{uuid.uuid4().hex}@example.com",
        password_hash=hash_password(STAFF_PASSWORD),
        role=role,
    )
    session.add(user)
    await session.flush()
    return user


async def act_as(client: AsyncClient, user: User, password: str = STAFF_PASSWORD) -> None:
    client.cookies.clear()
    await login(client, user.email, password)


async def become_moderator(client: AsyncClient, session: AsyncSession) -> User:
    """There is no self-registration for moderators, so the account is seeded and then logged in."""
    user = await seed_staff(session, UserRole.MODERATOR)
    await act_as(client, user)
    return user


async def register_second_seller(client: AsyncClient, session: AsyncSession) -> None:
    """A seller registration replaces the cookies, so the client acts as the new account."""
    client.cookies.clear()
    await register_seller(client, session, email=f"seller-{uuid.uuid4().hex}@example.com")


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


@dataclass
class Shop:
    """A seller admitted to the platform, with a storefront on the air."""

    business_id: str
    seller_id: str
    subdomain: str
    seller: dict[str, str]
    moderator: dict[str, str]


def switch(client: AsyncClient, cookies: dict[str, str]) -> None:
    client.cookies.clear()
    client.cookies.update(cookies)


async def anonymous(client: AsyncClient) -> None:
    client.cookies.clear()


async def confirm_email(session: AsyncSession, user_id: str) -> None:
    """Marks the address as answered for, the way a letter would.

    Set on the row rather than walked through a link: the token exists only inside the letter,
    and a test about shops should not have to compose and read one. What the flow itself does
    is covered where it belongs, in test_email_verification.py.
    """
    user = await session.get(User, uuid.UUID(user_id))
    assert user is not None
    user.email_verified_at = datetime.now(UTC)
    await session.flush()


async def a_live_shop(client: AsyncClient, session: AsyncSession, subdomain: str) -> Shop:
    # cookies restored by switch() carry no domain, so a fresh Set-Cookie would sit beside
    # them rather than replace them — the jar is emptied before a new session starts
    client.cookies.clear()
    registered = await register_seller(client, email=f"seller-{uuid.uuid4().hex}@example.com")
    business_id = str(registered.json()["business"]["id"])
    seller_id = str(registered.json()["user"]["id"])
    # opening a shop needs a confirmed address, which is what a real seller does first
    await confirm_email(session, seller_id)
    created = await client.post(
        STORES_URL, json={"subdomain": subdomain}, headers=csrf_headers(client)
    )
    assert created.status_code == 201
    seller = dict(client.cookies)

    await become_moderator(client, session)
    approved = await client.post(
        f"{BUSINESS_MODERATION}/{business_id}/approve", headers=csrf_headers(client)
    )
    assert approved.status_code == 200
    return Shop(business_id, seller_id, subdomain, seller, dict(client.cookies))


async def a_product(
    client: AsyncClient,
    session: AsyncSession,
    shop: Shop,
    *,
    category_slug: str = "smartphones",
    **fields: Any,
) -> str:
    switch(client, shop.seller)
    category = await seeded_category(session, category_slug)
    created = await create_product(client, category.id, **fields)
    assert created.status_code == 201
    return str(created.json()["id"])


async def a_published_product(
    client: AsyncClient, session: AsyncSession, shop: Shop, **fields: Any
) -> str:
    product_id = await a_product(client, session, shop, **fields)
    switch(client, shop.moderator)
    approved = await client.post(
        f"{PRODUCT_MODERATION}/{product_id}/approve", headers=csrf_headers(client)
    )
    assert approved.status_code == 200
    return product_id
