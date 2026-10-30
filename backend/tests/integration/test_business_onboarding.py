"""The way out of a seller account that has nothing to sell from.

Registering on the public form asks for the shop's details on the way in, so that path never
comes here. `scripts.grant_role` cannot ask: it knows an address and a role, and a business
needs a legal name and a name to trade under — both NOT NULL on the table. Such an account
lands in a cabinet with the shop section simply missing and no way forward.
"""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models import Business, BusinessStatus, User, UserRole
from tests.integration.conftest import csrf_headers, login, register_buyer, register_seller

pytestmark = pytest.mark.integration

URL = "/api/v1/users/me/business"
PASSWORD = "a-seller-password-1"
DETAILS = {"legal_name": "ИП Петров", "display_name": "Лавка Петрова"}


async def a_seller_without_a_business(client: AsyncClient, session: AsyncSession) -> User:
    """Exactly the state a granted role leaves behind: the account exists, the shop does not."""
    user = User(
        email=f"granted-seller-{uuid.uuid4().hex}@example.com",
        password_hash=hash_password(PASSWORD),
        role=UserRole.SELLER,
    )
    session.add(user)
    await session.flush()
    client.cookies.clear()
    await login(client, user.email, PASSWORD)
    return user


async def test_a_seller_without_a_business_can_open_one(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    await a_seller_without_a_business(api_client, session)

    response = await api_client.post(URL, json=DETAILS, headers=csrf_headers(api_client))

    assert response.status_code == 201
    body = response.json()
    assert body["display_name"] == "Лавка Петрова"
    # like any other application: it waits for a moderator rather than opening a shop
    assert body["status"] == BusinessStatus.PENDING.value


async def test_the_cabinet_can_read_it_straight_afterwards(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    """The screen redirects here when the business is missing, so a business that is created
    and then not visible would send the seller round in a circle."""
    await a_seller_without_a_business(api_client, session)

    await api_client.post(URL, json=DETAILS, headers=csrf_headers(api_client))

    assert (await api_client.get(URL)).status_code == 200


async def test_a_second_one_is_refused(api_client: AsyncClient, session: AsyncSession) -> None:
    """One seller, one business — and the unique index is what decides, so two taps on a slow
    connection cannot both pass a look-first check."""
    await a_seller_without_a_business(api_client, session)
    await api_client.post(URL, json=DETAILS, headers=csrf_headers(api_client))

    again = await api_client.post(URL, json=DETAILS, headers=csrf_headers(api_client))

    assert again.status_code == 409
    assert again.json()["error"]["code"] == "business_exists"


async def test_a_seller_who_registered_with_a_password_already_has_one(
    api_client: AsyncClient,
) -> None:
    await register_seller(api_client)

    refused = await api_client.post(URL, json=DETAILS, headers=csrf_headers(api_client))

    assert refused.status_code == 409


async def test_a_buyer_does_not_get_a_shop_this_way(api_client: AsyncClient) -> None:
    """Otherwise the role on the account would mean nothing: anybody could become a seller by
    asking the right address."""
    await register_buyer(api_client)

    refused = await api_client.post(URL, json=DETAILS, headers=csrf_headers(api_client))

    assert refused.status_code == 403


async def test_a_stranger_does_not_get_one_either(api_client: AsyncClient) -> None:
    """Refused by the CSRF guard before anything asks who they are — a caller with no session
    has no token to echo, so the question of identity never arises."""
    api_client.cookies.clear()

    refused = await api_client.post(URL, json=DETAILS)

    assert refused.status_code == 403
    assert (await api_client.get(URL)).status_code == 401


async def test_the_phone_is_recorded_because_nobody_ever_asked_for_it(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    """A shop a moderator cannot telephone is a shop a moderator cannot check, and this path
    never asked."""
    seller = await a_seller_without_a_business(api_client, session)

    await api_client.post(
        URL, json={**DETAILS, "phone": "+37410123456"}, headers=csrf_headers(api_client)
    )

    await session.refresh(seller)
    assert seller.phone == "+37410123456"


async def test_a_number_the_account_already_had_is_left_alone(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    """Changing it is a different act with a different screen; this one must not do it by
    accident on the way past."""
    seller = await a_seller_without_a_business(api_client, session)
    seller.phone = "+37410000000"
    await session.flush()

    await api_client.post(
        URL, json={**DETAILS, "phone": "+37410123456"}, headers=csrf_headers(api_client)
    )

    await session.refresh(seller)
    assert seller.phone == "+37410000000"


async def test_the_details_are_checked(api_client: AsyncClient, session: AsyncSession) -> None:
    await a_seller_without_a_business(api_client, session)

    refused = await api_client.post(
        URL, json={"legal_name": "a", "display_name": ""}, headers=csrf_headers(api_client)
    )

    assert refused.status_code == 422
    assert (await session.execute(select(Business))).scalars().all() == []
