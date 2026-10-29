"""What the allowances do to somebody standing at the door.

Two properties matter more than the numbers. A flood has to become expensive for whoever is
sending it — otherwise `/auth/login` is a way to spend the machine's CPU on argon2 for free.
And the owner of an account must never be shut out of it by somebody else's guessing, which
is why the per-account limit slows instead of refusing.
"""

import time
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps.rate_limit import LOGIN_ATTEMPTS, LOGIN_FREE_ATTEMPTS, REGISTRATION_ATTEMPTS
from tests.integration.conftest import BUYER_PAYLOAD, login, register_buyer

pytestmark = pytest.mark.integration

LOGIN_URL = "/api/v1/auth/login"
EMAIL = "buyer@example.com"
PASSWORD = "buyer-password-1"
WRONG = "not-the-password-at-all"


async def _failed_login(client: AsyncClient, email: str) -> int:
    response = await client.post(LOGIN_URL, json={"email": email, "password": WRONG})
    return response.status_code


async def test_a_flood_from_one_address_is_refused(api_client: AsyncClient) -> None:
    """Distinct addresses each time, so this meets the per-address allowance rather than the
    per-account delay — which is the shape an attack actually has."""
    for attempt in range(LOGIN_ATTEMPTS):
        status = await _failed_login(api_client, f"nobody-{attempt}@example.com")
        assert status == 401, f"attempt {attempt} should still be served"

    response = await api_client.post(
        LOGIN_URL, json={"email": "one-too-many@example.com", "password": WRONG}
    )

    assert response.status_code == 429
    assert response.json()["error"]["code"] == "too_many_requests"


async def test_a_refusal_says_when_to_come_back(api_client: AsyncClient) -> None:
    """A client that cannot read Russian still has to learn how long to wait."""
    for attempt in range(LOGIN_ATTEMPTS):
        await _failed_login(api_client, f"nobody-{attempt}@example.com")

    response = await api_client.post(LOGIN_URL, json={"email": EMAIL, "password": WRONG})

    assert response.status_code == 429
    assert int(response.headers["retry-after"]) >= 1


async def test_registering_in_bulk_is_refused(api_client: AsyncClient) -> None:
    for _ in range(REGISTRATION_ATTEMPTS):
        api_client.cookies.clear()
        await register_buyer(api_client, email=f"buyer-{uuid.uuid4().hex}@example.com")

    api_client.cookies.clear()
    response = await register_buyer(api_client, email=f"buyer-{uuid.uuid4().hex}@example.com")

    assert response.status_code == 429


async def test_guessing_one_account_gets_slower(api_client: AsyncClient) -> None:
    """Slower, and never refused: the limit must not become a way to lock somebody out of
    their own account by guessing at it from anywhere."""
    for _ in range(LOGIN_FREE_ATTEMPTS):
        assert await _failed_login(api_client, EMAIL) == 401

    started = time.monotonic()
    status = await _failed_login(api_client, EMAIL)
    waited = time.monotonic() - started

    assert status == 401, "the owner's account is slowed, never shut"
    assert waited >= 0.4, f"the attempt after the free ones should be made to wait, waited {waited}"


async def test_the_owner_still_gets_in_after_somebody_guessed(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    """The whole reason this limit delays rather than refuses."""
    await register_buyer(api_client)
    api_client.cookies.clear()
    for _ in range(LOGIN_FREE_ATTEMPTS + 1):
        await _failed_login(api_client, EMAIL)

    response = await login(api_client, EMAIL, PASSWORD)

    assert response.status_code == 200


async def test_a_known_and_an_unknown_address_are_slowed_alike(api_client: AsyncClient) -> None:
    """Otherwise the wait itself answers "does this account exist", which is the question the
    identical wording of the refusal exists to avoid answering."""
    await register_buyer(api_client)
    api_client.cookies.clear()

    for _ in range(LOGIN_FREE_ATTEMPTS):
        await _failed_login(api_client, EMAIL)
        await _failed_login(api_client, "nobody@example.com")

    started = time.monotonic()
    await _failed_login(api_client, EMAIL)
    known = time.monotonic() - started

    started = time.monotonic()
    await _failed_login(api_client, "nobody@example.com")
    unknown = time.monotonic() - started

    assert known >= 0.4 and unknown >= 0.4, f"known {known}, unknown {unknown}"


async def test_signing_in_clears_what_the_guessing_built_up(api_client: AsyncClient) -> None:
    await register_buyer(api_client)
    api_client.cookies.clear()
    for _ in range(LOGIN_FREE_ATTEMPTS + 1):
        await _failed_login(api_client, EMAIL)
    await login(api_client, EMAIL, BUYER_PAYLOAD["password"])

    started = time.monotonic()
    await _failed_login(api_client, EMAIL)
    waited = time.monotonic() - started

    assert waited < 0.4, f"the tally should have been forgotten, waited {waited}"
