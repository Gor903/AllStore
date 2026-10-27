import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import UserRole
from tests.integration.conftest import (
    Shop,
    a_live_shop,
    a_product,
    a_published_product,
    act_as,
    csrf_headers,
    register_seller,
    seed_staff,
    switch,
)

pytestmark = pytest.mark.integration

SEARCH = "/api/v1/moderation/catalog"
PRODUCTS_URL = "/api/v1/products"


async def found(client: AsyncClient, query: str) -> list[dict[str, object]]:
    response = await client.get(SEARCH, params={"q": query})
    assert response.status_code == 200
    items: list[dict[str, object]] = response.json()["items"]
    return items


async def test_a_moderator_finds_a_published_product_outside_the_queue(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    """The queue only holds what is pending; a complaint is about what is already selling."""
    shop = await a_live_shop(api_client, session, "cups")
    await a_published_product(api_client, session, shop, name="Кружка керамическая")

    assert [item["name"] for item in await found(api_client, "Кружка")] == ["Кружка керамическая"]


async def test_the_search_finds_a_product_by_its_shop(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    shop = await a_live_shop(api_client, session, "cups")
    await a_published_product(api_client, session, shop, name="Кружка керамическая")

    # a moderator sent after a shop rarely knows the name of the item
    assert len(await found(api_client, "Тестовый магазин")) == 1


async def test_the_search_finds_part_of_a_word(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    shop = await a_live_shop(api_client, session, "cups")
    await a_published_product(api_client, session, shop, name="Кружка керамическая")

    assert len(await found(api_client, "керам")) == 1


async def test_the_search_reaches_every_status(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    shop = await a_live_shop(api_client, session, "cups")
    await a_product(api_client, session, shop, name="Ждёт проверки")
    await a_published_product(api_client, session, shop, name="Уже на полке")
    switch(api_client, shop.moderator)

    assert {item["name"] for item in await found(api_client, "проверки")} == {"Ждёт проверки"}
    assert {item["name"] for item in await found(api_client, "полке")} == {"Уже на полке"}


async def test_an_archived_product_is_not_found(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    """The seller has taken it off the shelf themselves — there is nothing to moderate."""
    shop = await a_live_shop(api_client, session, "cups")
    product_id = await a_product(api_client, session, shop, name="Снятая с продажи")
    switch(api_client, shop.seller)
    await api_client.delete(f"{PRODUCTS_URL}/{product_id}", headers=csrf_headers(api_client))
    switch(api_client, shop.moderator)

    assert await found(api_client, "Снятая") == []


async def test_a_wildcard_does_not_return_the_whole_catalogue(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    shop = await a_live_shop(api_client, session, "cups")
    await a_published_product(api_client, session, shop, name="Кружка керамическая")

    assert await found(api_client, "%") == []


async def test_a_search_without_a_query_is_refused(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    """An empty query would hand over the whole catalogue page by page instead of a search."""
    await act_as(api_client, await seed_staff(session, UserRole.MODERATOR))

    assert (await api_client.get(SEARCH)).status_code == 422
    assert (await api_client.get(SEARCH, params={"q": ""})).status_code == 422


async def test_the_result_carries_what_a_moderator_judges_by(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    shop: Shop = await a_live_shop(api_client, session, "cups")
    await a_published_product(api_client, session, shop, name="Кружка керамическая")

    item = (await found(api_client, "Кружка"))[0]

    # a pair of identifiers is not something anyone can judge
    assert item["category_name"] == "Смартфоны и гаджеты"
    assert item["seller_name"] == "Тестовый магазин"
    assert item["subdomain"] == "cups"
    assert item["publication_status"] == "published"


async def test_an_admin_may_search_too(api_client: AsyncClient, session: AsyncSession) -> None:
    shop = await a_live_shop(api_client, session, "cups")
    await a_published_product(api_client, session, shop, name="Кружка керамическая")
    await act_as(api_client, await seed_staff(session, UserRole.ADMIN))

    assert len(await found(api_client, "Кружка")) == 1


@pytest.mark.parametrize("role", [UserRole.BUYER, UserRole.SELLER])
async def test_nobody_else_searches_the_whole_catalogue(
    api_client: AsyncClient, session: AsyncSession, role: UserRole
) -> None:
    api_client.cookies.clear()
    if role is UserRole.SELLER:
        await register_seller(api_client, email=f"seller-{uuid.uuid4().hex}@example.com")
    else:
        await act_as(api_client, await seed_staff(session, role))

    assert (await api_client.get(SEARCH, params={"q": "Кружка"})).status_code == 403


async def test_an_anonymous_visitor_does_not_search_it_either(api_client: AsyncClient) -> None:
    assert (await api_client.get(SEARCH, params={"q": "Кружка"})).status_code == 401
