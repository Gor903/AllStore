"""Confirming that an address belongs to the person who typed it.

`email_verified_at` was declared on the second stage and never written to by anything. These
tests are what makes it mean something: an address is the account's own once somebody has
answered a letter at it, and opening a shop waits for that.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.mail import Letter
from app.models import Session, User, UserRole
from app.services import notifications
from tests.integration.conftest import (
    BUYER_PAYLOAD,
    csrf_headers,
    login,
    register_buyer,
    register_seller,
)

pytestmark = pytest.mark.integration

CONFIRM = "/api/v1/auth/email/confirm"
RESEND = "/api/v1/auth/email/verify"
CHANGE = "/api/v1/auth/email"
STORES = "/api/v1/stores"
EMAIL = "buyer@example.com"
PASSWORD = str(BUYER_PAYLOAD["password"])


@pytest.fixture
def letters(monkeypatch: pytest.MonkeyPatch) -> list[Letter]:
    """Catches every letter on its way to the wire, in order."""
    caught: list[Letter] = []

    async def fake_deliver(settings: object, letter: Letter) -> None:
        caught.append(letter)

    monkeypatch.setattr(notifications, "deliver", fake_deliver)
    return caught


def _token(letter: Letter) -> str:
    return letter.body.split("token=", 1)[1].split()[0]


async def test_registering_asks_the_address_to_answer(
    api_client: AsyncClient, letters: list[Letter]
) -> None:
    await register_buyer(api_client)

    assert [letter.to for letter in letters] == [EMAIL]
    assert "/email/confirm?token=" in letters[0].body


async def test_a_new_account_is_not_verified_yet(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    await register_buyer(api_client)

    user = (await session.execute(select(User))).scalars().one()
    assert user.email_verified_at is None


async def test_opening_the_link_makes_the_address_the_accounts_own(
    api_client: AsyncClient, session: AsyncSession, letters: list[Letter]
) -> None:
    await register_buyer(api_client)

    response = await api_client.post(CONFIRM, json={"token": _token(letters[0])})

    assert response.status_code == 200
    user = (await session.execute(select(User))).scalars().one()
    assert user.email_verified_at is not None


async def test_confirming_your_own_address_does_not_sign_you_out(
    api_client: AsyncClient, letters: list[Letter]
) -> None:
    """The browser being asked to confirm is usually the one signed in. Ending its session
    would make confirming feel like a punishment."""
    await register_buyer(api_client)

    await api_client.post(CONFIRM, json={"token": _token(letters[0])})

    assert (await api_client.get("/api/v1/users/me")).status_code == 200


async def test_the_link_works_only_once(api_client: AsyncClient, letters: list[Letter]) -> None:
    await register_buyer(api_client)
    token = _token(letters[0])
    await api_client.post(CONFIRM, json={"token": token})

    again = await api_client.post(CONFIRM, json={"token": token})

    assert again.status_code == 409
    assert again.json()["error"]["code"] == "invalid_verification_token"


async def test_a_token_nobody_issued_opens_nothing(api_client: AsyncClient) -> None:
    await register_buyer(api_client)

    response = await api_client.post(CONFIRM, json={"token": "never-issued"})

    assert response.status_code == 409


async def test_asking_again_puts_the_earlier_link_out_of_use(
    api_client: AsyncClient, letters: list[Letter]
) -> None:
    """A letter dug out of an old inbox must not be able to undo a later decision."""
    await register_buyer(api_client)
    first = _token(letters[0])

    await api_client.post(RESEND, headers=csrf_headers(api_client))

    assert (await api_client.post(CONFIRM, json={"token": first})).status_code == 409
    assert (await api_client.post(CONFIRM, json={"token": _token(letters[-1])})).status_code == 200


async def test_a_shop_waits_for_the_address(
    api_client: AsyncClient, session: AsyncSession, letters: list[Letter]
) -> None:
    """The one gate. Opening a shop puts a name and a storefront in front of strangers, and
    the platform is the one presenting it."""
    await register_seller(api_client)

    refused = await api_client.post(
        STORES, json={"subdomain": "cups"}, headers=csrf_headers(api_client)
    )

    assert refused.status_code == 403
    assert refused.json()["error"]["code"] == "email_not_verified"

    await api_client.post(CONFIRM, json={"token": _token(letters[0])})
    allowed = await api_client.post(
        STORES, json={"subdomain": "cups"}, headers=csrf_headers(api_client)
    )

    assert allowed.status_code == 201


async def test_a_buyer_reaching_for_a_shop_is_told_about_the_role_not_the_address(
    api_client: AsyncClient,
) -> None:
    """Being asked to confirm an address implies the shop was otherwise theirs to open."""
    await register_buyer(api_client)

    response = await api_client.post(
        STORES, json={"subdomain": "cups"}, headers=csrf_headers(api_client)
    )

    assert response.json()["error"]["code"] == "permission_denied"


async def test_moving_waits_for_the_new_address_and_tells_the_old_one(
    api_client: AsyncClient, session: AsyncSession, letters: list[Letter]
) -> None:
    await register_buyer(api_client)
    letters.clear()

    await api_client.post(
        CHANGE,
        json={"email": "moved@example.com", "current_password": PASSWORD},
        headers=csrf_headers(api_client),
    )

    assert [letter.to for letter in letters] == ["moved@example.com", EMAIL]
    # the old address is told, because whoever still reads it is the only one who can notice
    assert "смена адреса" in letters[1].subject.lower()
    user = (await session.execute(select(User))).scalars().one()
    assert user.email == EMAIL, "nothing moves until the new address answers"


async def test_the_old_address_still_works_while_the_new_one_has_not_answered(
    api_client: AsyncClient,
) -> None:
    """A typo in the new address must not lock somebody out of an account whose password they
    still know — which is exactly what changing the login on submit used to do."""
    await register_buyer(api_client)
    await api_client.post(
        CHANGE,
        json={"email": "typo@example.com", "current_password": PASSWORD},
        headers=csrf_headers(api_client),
    )
    api_client.cookies.clear()

    assert (await login(api_client, EMAIL, PASSWORD)).status_code == 200


async def test_opening_the_link_moves_the_account_and_ends_its_sessions(
    api_client: AsyncClient, session: AsyncSession, letters: list[Letter]
) -> None:
    await register_buyer(api_client)
    letters.clear()
    await api_client.post(
        CHANGE,
        json={"email": "moved@example.com", "current_password": PASSWORD},
        headers=csrf_headers(api_client),
    )

    response = await api_client.post(CONFIRM, json={"token": _token(letters[0])})

    assert response.status_code == 200
    user = (await session.execute(select(User))).scalars().one()
    assert user.email == "moved@example.com"
    assert user.email_verified_at is not None
    live = await session.execute(
        select(Session).where(Session.user_id == user.id, Session.revoked_at.is_(None))
    )
    assert live.scalars().all() == [], "half the credentials changed, so the sessions end"


async def test_a_link_to_an_address_somebody_took_in_the_meantime_is_refused(
    api_client: AsyncClient, session: AsyncSession, letters: list[Letter]
) -> None:
    """The unique index is what actually decides; this check exists so the answer is a
    sentence rather than a constraint violation."""
    await register_buyer(api_client)
    letters.clear()
    await api_client.post(
        CHANGE,
        json={"email": "contested@example.com", "current_password": PASSWORD},
        headers=csrf_headers(api_client),
    )
    session.add(User(email="contested@example.com", password_hash="x", role=UserRole.BUYER))
    await session.flush()

    response = await api_client.post(CONFIRM, json={"token": _token(letters[0])})

    assert response.status_code == 409


async def test_moving_to_the_address_it_already_is_gets_refused(api_client: AsyncClient) -> None:
    """Answering "check your email" would send somebody to wait for a letter about an address
    they are already using."""
    await register_buyer(api_client)

    response = await api_client.post(
        CHANGE,
        json={"email": EMAIL, "current_password": PASSWORD},
        headers=csrf_headers(api_client),
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "same_email"
