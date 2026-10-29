"""What a mutating request has to prove about where it came from.

Three checks, and each catches what the others cannot. The token says the caller could read a
cookie a cross-site page cannot. `Sec-Fetch-Site` is the browser's own account of where it
sent the request from, which a page cannot write. `Origin` is checked against the addresses we
expect to be called from, for the browsers that do not send the first.
"""

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.db.session import get_session
from app.deps.settings import settings_dep
from app.main import create_app
from tests.integration.conftest import csrf_headers, register_buyer

pytestmark = pytest.mark.integration

LOGOUT = "/api/v1/auth/logout"
OURS = "https://allstore.am"


async def _client(session: AsyncSession, settings: Settings) -> AsyncClient:
    app = create_app()

    async def _use_test_session() -> AsyncSession:
        return session

    app.dependency_overrides[get_session] = _use_test_session
    app.dependency_overrides[settings_dep] = lambda: settings
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def test_a_cross_site_request_is_refused_even_with_the_token(
    api_client: AsyncClient,
) -> None:
    """The browser is telling us where it sent this from, and no forged page can lie about it.
    The token travelling with it changes nothing — if it is there, it was stolen."""
    await register_buyer(api_client)
    headers = {**csrf_headers(api_client), "sec-fetch-site": "cross-site"}

    response = await api_client.post(LOGOUT, headers=headers)

    assert response.status_code == 403


async def test_our_own_pages_are_served(api_client: AsyncClient) -> None:
    """`same-origin` and `same-site` are both ours: a storefront subdomain calling the API is
    the second, and refusing it would take the complaint button off every shop."""
    await register_buyer(api_client)

    for site in ("same-origin", "same-site", "none"):
        api_client.cookies.clear()
        await register_buyer(api_client, email=f"buyer-{site}@example.com")
        headers = {**csrf_headers(api_client), "sec-fetch-site": site}

        response = await api_client.post(LOGOUT, headers=headers)

        assert response.status_code == 204, f"{site} should be served"


async def test_an_origin_we_do_not_know_is_refused(session: AsyncSession) -> None:
    settings = get_settings().model_copy(update={"allowed_origins": (OURS,)})
    client = await _client(session, settings)
    async with client:
        await register_buyer(client)
        headers = {**csrf_headers(client), "origin": "https://not-us.example"}

        response = await client.post(LOGOUT, headers=headers)

        assert response.status_code == 403
        assert response.json()["error"]["code"] == "permission_denied"


async def test_our_own_origin_is_served(session: AsyncSession) -> None:
    settings = get_settings().model_copy(update={"allowed_origins": (OURS,)})
    client = await _client(session, settings)
    async with client:
        await register_buyer(client)
        headers = {**csrf_headers(client), "origin": OURS}

        response = await client.post(LOGOUT, headers=headers)

        assert response.status_code == 204


async def test_a_missing_origin_is_not_an_offence(session: AsyncSession) -> None:
    """Browsers omit it on plenty of ordinary requests, and a caller that is not a browser has
    none to send. The token still has to match."""
    settings = get_settings().model_copy(update={"allowed_origins": (OURS,)})
    client = await _client(session, settings)
    async with client:
        await register_buyer(client)

        response = await client.post(LOGOUT, headers=csrf_headers(client))

        assert response.status_code == 204


async def test_nothing_configured_means_the_question_is_not_asked(session: AsyncSession) -> None:
    """An environment that named no origins gets the token check and nothing more — the
    alternative is refusing every request on a stand nobody configured."""
    settings = get_settings().model_copy(update={"allowed_origins": (), "cors_origins": []})
    client = await _client(session, settings)
    async with client:
        await register_buyer(client)
        headers = {**csrf_headers(client), "origin": "https://anywhere.example"}

        response = await client.post(LOGOUT, headers=headers)

        assert response.status_code == 204
