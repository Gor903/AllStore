import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from httpx import AsyncClient, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import hash_password
from app.core.totp import code_for, generate_secret, step_at
from app.core.vault import lock
from app.models import Category, TotpCredential, User, UserRole

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


async def seed_staff(session: AsyncSession, role: UserRole, *, second_factor: bool = True) -> User:
    """Moderators and administrators have no self-registration, so they are seeded.

    An administrator seeded here is the only one the platform may have: the unique partial
    index on the role sees to that, and a test that wants two is describing a platform this
    one is not.

    Enrolled in a second factor by default, because that is what a staff account that can do
    anything looks like — without one it is stopped at the setup screen on every request, and
    a suite full of accounts in that state would be testing the gate over and over instead of
    the thing each test is about. Pass `second_factor=False` to get an account that still owes
    one, which is what the tests about the gate itself want.
    """
    user = User(
        email=f"{role}-{uuid.uuid4().hex}@example.com",
        password_hash=hash_password(STAFF_PASSWORD),
        role=role,
    )
    session.add(user)
    await session.flush()
    if second_factor:
        await enrol_second_factor(session, user)
    return user


# What was enrolled for whom, so that `act_as` can answer the challenge without a second
# connection — the account it needs to read lives in a transaction that is never committed.
SECRETS: dict[uuid.UUID, str] = {}


async def enrol_second_factor(session: AsyncSession, user: User) -> str:
    """Gives the account a confirmed authenticator and returns its secret."""
    secret = generate_secret()
    session.add(
        TotpCredential(
            user_id=user.id,
            secret_encrypted=lock(get_settings(), secret),
            confirmed_at=datetime.now(UTC),
        )
    )
    await session.flush()
    SECRETS[user.id] = secret
    return secret


async def act_as(client: AsyncClient, user: User, password: str = STAFF_PASSWORD) -> None:
    """Signs in, answering the second factor when the account has one.

    Staff accounts do, so signing one in is two requests rather than one — the password stops
    at a code and the code opens the session. Hidden here because nearly every test wants
    "this moderator is signed in" rather than the two steps it takes.
    """
    client.cookies.clear()
    answer = await login(client, user.email, password)
    if answer.status_code == 401 and answer.json()["error"]["code"] == "totp_required":
        await answer_second_factor(client, user)


async def answer_second_factor(client: AsyncClient, user: User) -> Response:
    """Finishes a sign-in that paused, with the code the account's authenticator would show.

    Falls forward a step when the current code has already been spent. A code is good once,
    and a test that signs the same account in twice inside thirty seconds would otherwise be
    told so — correctly. A person waits for the next code; this does the same thing without
    making the suite wait half a minute, using the step ahead, which is inside the drift the
    server accepts.
    """
    answer = await client.post("/api/v1/auth/login/totp", json={"code": code_now(user)})
    if answer.status_code == 403:
        answer = await client.post(
            "/api/v1/auth/login/totp", json={"code": code_now(user, ahead=1)}
        )
    return answer


def code_now(user: User, ahead: int = 0) -> str:
    return code_for(SECRETS[user.id], step_at(time.time()) + ahead)


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
