"""The catalogue when words and meaning are searched together.

The search service is not started here — a function stands in for it. What is checked is not
the quality of a model (that is judged by hand on a live catalogue) but how backend treats its
answer: what it takes from it, what it trusts it about, and what it does when there is none.
"""

import uuid
from collections.abc import Awaitable, Callable
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.services import search_client
from tests.integration.conftest import csrf_headers
from tests.integration.test_catalog import (
    CATALOG_PRODUCTS,
    PRODUCT_MODERATION,
    a_live_shop,
    a_published_product,
    anonymous,
    switch,
)

pytestmark = pytest.mark.integration

SearchStub = Callable[[Settings, str, int], Awaitable[list[uuid.UUID]]]


@pytest.fixture
def with_search(monkeypatch: pytest.MonkeyPatch) -> Callable[[list[uuid.UUID]], None]:
    """Configures a search service that answers with exactly these products."""

    def configure(found: list[uuid.UUID]) -> None:
        settings = get_settings()
        monkeypatch.setattr(settings, "search_service_url", "http://search:8000")

        async def fake(_settings: Settings, _query: str, _limit: int) -> list[uuid.UUID]:
            return found

        monkeypatch.setattr(search_client, "semantic_ids", fake)

    return configure


async def test_a_product_without_the_words_is_found_by_meaning(
    api_client: AsyncClient,
    session: AsyncSession,
    with_search: Callable[[list[uuid.UUID]], None],
) -> None:
    """The whole point: the words of the query are nowhere in the product, and it is the one."""
    shop = await a_live_shop(api_client, session, "cups")
    vase = await a_published_product(api_client, session, shop, name="Ваза керамическая")
    with_search([uuid.UUID(vase)])
    await anonymous(api_client)

    body = (await api_client.get(CATALOG_PRODUCTS, params={"q": "сосуд для букета"})).json()

    assert [item["id"] for item in body["items"]] == [vase]
    assert body["by_meaning"] == [vase]


async def test_the_words_still_win(
    api_client: AsyncClient,
    session: AsyncSession,
    with_search: Callable[[list[uuid.UUID]], None],
) -> None:
    """Exact search did not get worse: what matched by substring still comes first."""
    shop = await a_live_shop(api_client, session, "cups")
    exact = await a_published_product(api_client, session, shop, name="Ваза «Гюмри»")
    other = await a_published_product(api_client, session, shop, name="Плед шерстяной")
    with_search([uuid.UUID(other)])
    await anonymous(api_client)

    body = (await api_client.get(CATALOG_PRODUCTS, params={"q": "ваза"})).json()

    assert next(item["id"] for item in body["items"]) == exact
    assert body["by_meaning"] == [other]


async def test_a_hidden_product_does_not_leak_through_the_vector(
    api_client: AsyncClient,
    session: AsyncSession,
    with_search: Callable[[list[uuid.UUID]], None],
) -> None:
    """The index knows nothing about moderation, and must not.

    The service returned a product a moderator took off the shelf. Visibility is decided by
    backend, by the same rule as everywhere else — otherwise a hidden product would walk back
    into the catalogue through the search.
    """
    shop = await a_live_shop(api_client, session, "cups")
    hidden = await a_published_product(api_client, session, shop, name="Ваза «Гюмри»")
    switch(api_client, shop.moderator)
    await api_client.post(f"{PRODUCT_MODERATION}/{hidden}/hide", headers=csrf_headers(api_client))
    with_search([uuid.UUID(hidden)])
    await anonymous(api_client)

    body = (await api_client.get(CATALOG_PRODUCTS, params={"q": "сосуд для букета"})).json()

    assert body["items"] == []
    assert body["total"] == 0


async def test_a_product_of_another_shop_respects_the_filter(
    api_client: AsyncClient,
    session: AsyncSession,
    with_search: Callable[[list[uuid.UUID]], None],
) -> None:
    """What the buyer filtered by outranks what the search suggested: they asked for this shop."""
    first = await a_live_shop(api_client, session, "cups")
    stranger = await a_published_product(api_client, session, first, name="Ваза «Гюмри»")
    second = await a_live_shop(api_client, session, "mugs")
    await a_published_product(api_client, session, second, name="Кружка")
    with_search([uuid.UUID(stranger)])
    await anonymous(api_client)

    body = (await api_client.get(CATALOG_PRODUCTS, params={"q": "посуда", "store": "mugs"})).json()

    assert all(item["id"] != stranger for item in body["items"])


async def test_the_catalogue_answers_when_the_search_is_down(
    api_client: AsyncClient, session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Service unreachable: the listing quietly stays exact — not empty, and not an error."""
    shop = await a_live_shop(api_client, session, "cups")
    vase = await a_published_product(api_client, session, shop, name="Ваза «Гюмри»")
    settings = get_settings()
    monkeypatch.setattr(settings, "search_service_url", "http://search:8000")

    async def unreachable(*_args: Any, **_kwargs: Any) -> list[uuid.UUID]:
        # exactly what the client returns when the service did not answer
        return []

    monkeypatch.setattr(search_client, "semantic_ids", unreachable)
    await anonymous(api_client)

    body = (await api_client.get(CATALOG_PRODUCTS, params={"q": "ваза"})).json()

    assert [item["id"] for item in body["items"]] == [vase]
    assert body["by_meaning"] == []


async def test_without_a_service_nothing_changes(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    """Not configured at all — the path is the one that existed before this stage."""
    shop = await a_live_shop(api_client, session, "cups")
    vase = await a_published_product(api_client, session, shop, name="Ваза «Гюмри»")
    await anonymous(api_client)

    body = (await api_client.get(CATALOG_PRODUCTS, params={"q": "ваза"})).json()

    assert [item["id"] for item in body["items"]] == [vase]
    assert body["by_meaning"] == []


async def test_the_client_survives_a_broken_service(monkeypatch: pytest.MonkeyPatch) -> None:
    """The client raises nothing: the catalogue has no "search broke" branch to write."""
    settings = get_settings()
    monkeypatch.setattr(settings, "search_service_url", "http://127.0.0.1:1")

    assert await search_client.semantic_ids(settings, "ваза", 10) == []
    # and the ping about an edited product must not surface to the seller either
    await search_client.product_changed(settings, uuid.uuid4())
