"""Signing up, and the one thing the form must never answer.

Registration used to refuse a taken address out loud. It needs no password and anybody may
submit it, so that refusal was a way to ask whether a particular person has an account here —
walk a list of addresses through the form and read the answers. Now both outcomes get the same
sentence, the same status and no session, and the difference lives where it belongs: in who
receives a letter and what it says.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.mail import Letter
from app.models import Business, BusinessStatus, User, UserRole
from app.services import notifications
from tests.integration.conftest import BUYER_PAYLOAD, register_buyer, register_seller

pytestmark = pytest.mark.integration

BUYER_URL = "/api/v1/auth/register/buyer"
SELLER_URL = "/api/v1/auth/register/seller"
EMAIL = "buyer@example.com"


@pytest.fixture
def letters(monkeypatch: pytest.MonkeyPatch) -> list[Letter]:
    caught: list[Letter] = []

    def fake_deliver(settings: object, letter: Letter) -> None:
        caught.append(letter)

    monkeypatch.setattr(notifications, "deliver", fake_deliver)
    return caught


async def test_registering_creates_the_account(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    response = await api_client.post(BUYER_URL, json=BUYER_PAYLOAD)

    assert response.status_code == 202
    user = (await session.execute(select(User).where(User.email == EMAIL))).scalar_one()
    assert user.role is UserRole.BUYER
    assert user.email_verified_at is None


async def test_a_free_address_and_a_taken_one_answer_identically(
    api_client: AsyncClient,
) -> None:
    """The whole point. Status, body and cookies all have to match, because any one of them
    would answer the question on its own."""
    first = await api_client.post(BUYER_URL, json=BUYER_PAYLOAD)
    api_client.cookies.clear()

    second = await api_client.post(BUYER_URL, json=BUYER_PAYLOAD)

    assert first.status_code == second.status_code == 202
    assert first.json() == second.json()
    assert dict(first.cookies) == dict(second.cookies) == {}


async def test_the_letter_is_what_differs(api_client: AsyncClient, letters: list[Letter]) -> None:
    """A free address is asked to confirm itself; a taken one is told somebody tried."""
    await api_client.post(BUYER_URL, json=BUYER_PAYLOAD)
    assert "/email/confirm?token=" in letters[0].body
    letters.clear()

    await api_client.post(BUYER_URL, json=BUYER_PAYLOAD)

    assert len(letters) == 1
    assert letters[0].to == EMAIL
    assert "уже есть" in letters[0].body
    # nothing that would help somebody who is not the owner
    assert "token=" not in letters[0].body


async def test_registration_hands_out_no_session(api_client: AsyncClient) -> None:
    """Signing one person in and not the other is a difference visible without reading a word."""
    settings = get_settings()

    await api_client.post(BUYER_URL, json=BUYER_PAYLOAD)

    assert settings.session_cookie not in api_client.cookies
    assert (await api_client.get("/api/v1/users/me")).status_code == 401


async def test_the_address_is_lowercased_so_one_person_is_one_account(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    """Buyer@Example.com and buyer@example.com must not become two accounts."""
    await api_client.post(BUYER_URL, json=BUYER_PAYLOAD)

    await api_client.post(BUYER_URL, json={**BUYER_PAYLOAD, "email": "BUYER@example.com"})

    assert len((await session.execute(select(User))).scalars().all()) == 1


async def test_a_shared_phone_is_not_a_collision(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    """The number was never checked, so owning one was never ours to grant — migration 0028."""
    await api_client.post(BUYER_URL, json={**BUYER_PAYLOAD, "phone": "+37422222222"})

    await api_client.post(
        BUYER_URL,
        json={**BUYER_PAYLOAD, "email": "other@example.com", "phone": "+37422222222"},
    )

    assert len((await session.execute(select(User))).scalars().all()) == 2


async def test_a_short_password_is_still_refused_plainly(api_client: AsyncClient) -> None:
    """Validation is not enumeration: the answer is about what was typed, not about who
    exists."""
    response = await api_client.post(BUYER_URL, json={**BUYER_PAYLOAD, "password": "short"})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_failed"


async def test_an_invalid_address_is_refused(api_client: AsyncClient) -> None:
    response = await api_client.post(BUYER_URL, json={**BUYER_PAYLOAD, "email": "not-an-email"})

    assert response.status_code == 422


async def test_the_password_is_never_echoed_back(api_client: AsyncClient) -> None:
    response = await api_client.post(BUYER_URL, json=BUYER_PAYLOAD)

    assert str(BUYER_PAYLOAD["password"]) not in response.text


async def test_a_seller_gets_a_business_waiting_for_a_moderator(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    registered = await register_seller(api_client)

    assert registered.status_code == 202
    assert registered.json()["user"]["role"] == UserRole.SELLER
    assert registered.json()["business"]["status"] == BusinessStatus.PENDING
    stored = (await session.execute(select(Business))).scalar_one()
    assert stored.legal_name == 'ИП "Тестовый"'


async def test_a_seller_registration_still_needs_its_names(api_client: AsyncClient) -> None:
    response = await api_client.post(
        SELLER_URL,
        json={"email": "nolegal@example.com", "password": "seller-password-1", "display_name": "М"},
    )

    assert response.status_code == 422


async def test_the_helper_signs_people_in_the_way_every_other_test_expects(
    api_client: AsyncClient,
) -> None:
    """Registration no longer does it, so the helper does — otherwise the whole suite would
    be rewriting the same three lines."""
    await register_buyer(api_client)

    assert (await api_client.get("/api/v1/users/me")).status_code == 200
