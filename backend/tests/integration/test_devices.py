"""The devices an account is signed in on, and taking one of them away.

The screen exists for one question — "is somebody else in my account?" — and the answer has to
be actionable without knowing which line is the intruder. That is why signing out everywhere
else is a single button and not a selection.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models import Session
from tests.integration.conftest import BUYER_PAYLOAD, csrf_headers, login, register_buyer

pytestmark = pytest.mark.integration

DEVICES = "/api/v1/auth/sessions"
EMAIL = "buyer@example.com"
PASSWORD = str(BUYER_PAYLOAD["password"])


async def _second_device(client: AsyncClient) -> dict[str, str]:
    """Signing in again from a clean jar is what a second device looks like from here."""
    first = dict(client.cookies)
    client.cookies.clear()
    await login(client, EMAIL, PASSWORD)
    second = dict(client.cookies)
    client.cookies.clear()
    client.cookies.update(first)
    return second


async def test_one_device_is_listed_and_marked_as_this_one(api_client: AsyncClient) -> None:
    await register_buyer(api_client)

    body = (await api_client.get(DEVICES)).json()

    assert len(body["items"]) == 1
    assert body["items"][0]["current"] is True


async def test_a_second_sign_in_is_a_second_device(api_client: AsyncClient) -> None:
    await register_buyer(api_client)
    await _second_device(api_client)

    body = (await api_client.get(DEVICES)).json()

    assert len(body["items"]) == 2
    assert [item["current"] for item in body["items"]].count(True) == 1


async def test_renewing_does_not_look_like_a_new_device(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    """Two rows, one device. A list that grew every hour would be unreadable by the end of
    the week, and worse, it would hide the one line that mattered."""
    await register_buyer(api_client)
    await api_client.post("/api/v1/auth/renew", headers=csrf_headers(api_client))

    body = (await api_client.get(DEVICES)).json()

    assert len((await session.execute(select(Session))).scalars().all()) == 2
    assert len(body["items"]) == 1


async def test_the_list_never_carries_the_token(api_client: AsyncClient) -> None:
    """Not even a fragment. This is a screen people are told to check when something feels
    wrong, which makes it a screen an attacker reads too."""
    settings = get_settings()
    await register_buyer(api_client)
    token = api_client.cookies[settings.session_cookie]

    body = (await api_client.get(DEVICES)).text

    assert token not in body
    assert token[:8] not in body


async def test_signing_out_one_device_leaves_the_others(api_client: AsyncClient) -> None:
    await register_buyer(api_client)
    other = await _second_device(api_client)
    listed = (await api_client.get(DEVICES)).json()["items"]
    theirs = next(item for item in listed if not item["current"])

    response = await api_client.delete(
        f"{DEVICES}/{theirs['id']}", headers=csrf_headers(api_client)
    )

    assert response.status_code == 204
    assert (await api_client.get("/api/v1/users/me")).status_code == 200
    api_client.cookies.clear()
    api_client.cookies.update(other)
    assert (await api_client.get("/api/v1/users/me")).status_code == 401


async def test_signing_out_everywhere_else_keeps_the_one_asking(
    api_client: AsyncClient,
) -> None:
    await register_buyer(api_client)
    other = await _second_device(api_client)

    response = await api_client.delete(DEVICES, headers=csrf_headers(api_client))

    assert response.status_code == 204
    assert (await api_client.get("/api/v1/users/me")).status_code == 200
    api_client.cookies.clear()
    api_client.cookies.update(other)
    assert (await api_client.get("/api/v1/users/me")).status_code == 401


async def test_a_device_from_somebody_elses_list_is_not_there(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    """Reads as missing rather than as forbidden: "forbidden" would confirm the identifier
    belongs to somebody."""
    await register_buyer(api_client)
    api_client.cookies.clear()
    await register_buyer(api_client, email="someone-else@example.com")
    stranger = (await api_client.get(DEVICES)).json()["items"][0]["id"]
    api_client.cookies.clear()
    await login(api_client, EMAIL, PASSWORD)

    response = await api_client.delete(f"{DEVICES}/{stranger}", headers=csrf_headers(api_client))

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "session_not_found"


async def test_the_list_needs_a_session(api_client: AsyncClient) -> None:
    assert (await api_client.get(DEVICES)).status_code == 401


async def test_revoking_without_the_csrf_header_is_refused(api_client: AsyncClient) -> None:
    await register_buyer(api_client)
    listed = (await api_client.get(DEVICES)).json()["items"][0]["id"]

    response = await api_client.delete(f"{DEVICES}/{listed}")

    assert response.status_code == 403
