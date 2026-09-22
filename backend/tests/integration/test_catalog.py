import uuid
from dataclasses import dataclass
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.integration.conftest import (
    PRODUCTS_URL,
    become_moderator,
    create_product,
    csrf_headers,
    register_seller,
    seeded_category,
)

pytestmark = pytest.mark.integration

CATALOG_PRODUCTS = "/api/v1/catalog/products"
CATALOG_STORES = "/api/v1/catalog/stores"
CATALOG_CATEGORIES = "/api/v1/catalog/categories"
STORES_URL = "/api/v1/stores"
BUSINESS_MODERATION = "/api/v1/moderation/businesses"
PRODUCT_MODERATION = "/api/v1/moderation/products"

PUBLIC_PRODUCT_FIELDS = {
    "id",
    "name",
    "description",
    "price",
    "currency",
    "availability_status",
    "category",
    "store",
    "images",
    "created_at",
}


@dataclass
class Shop:
    """A seller admitted to the platform, with a storefront on the air."""

    business_id: str
    subdomain: str
    seller: dict[str, str]
    moderator: dict[str, str]


def switch(client: AsyncClient, cookies: dict[str, str]) -> None:
    client.cookies.clear()
    client.cookies.update(cookies)


async def a_live_shop(client: AsyncClient, session: AsyncSession, subdomain: str) -> Shop:
    # cookies restored by switch() carry no domain, so a fresh Set-Cookie would sit beside
    # them rather than replace them — the jar is emptied before a new session starts
    client.cookies.clear()
    registered = await register_seller(client, email=f"seller-{uuid.uuid4().hex}@example.com")
    business_id = str(registered.json()["business"]["id"])
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
    return Shop(business_id, subdomain, seller, dict(client.cookies))


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


async def anonymous(client: AsyncClient) -> None:
    client.cookies.clear()


async def test_the_catalogue_shows_a_published_product(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    shop = await a_live_shop(api_client, session, "cups")
    product_id = await a_published_product(api_client, session, shop, name="Кружка керамическая")
    await anonymous(api_client)

    response = await api_client.get(CATALOG_PRODUCTS)

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    item = body["items"][0]
    assert item["id"] == product_id
    assert item["store"] == {"subdomain": "cups", "display_name": "Тестовый магазин"}
    assert item["category"]["slug"] == "smartphones"


async def test_the_catalogue_shows_nothing_internal(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    """The whole key set is compared: a field added by accident is caught here."""
    shop = await a_live_shop(api_client, session, "cups")
    await a_published_product(api_client, session, shop)
    await anonymous(api_client)

    item = (await api_client.get(CATALOG_PRODUCTS)).json()["items"][0]

    assert set(item) == PUBLIC_PRODUCT_FIELDS
    assert set(item["store"]) == {"subdomain", "display_name"}


async def test_a_product_is_readable_by_its_own_address(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    shop = await a_live_shop(api_client, session, "cups")
    product_id = await a_published_product(api_client, session, shop)
    await anonymous(api_client)

    response = await api_client.get(f"{CATALOG_PRODUCTS}/{product_id}")

    assert response.status_code == 200
    assert response.json()["id"] == product_id


async def test_a_product_awaiting_moderation_is_nowhere_to_be_seen(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    shop = await a_live_shop(api_client, session, "cups")
    product_id = await a_product(api_client, session, shop)
    await anonymous(api_client)

    assert (await api_client.get(CATALOG_PRODUCTS)).json()["total"] == 0
    assert (await api_client.get(f"{CATALOG_PRODUCTS}/{product_id}")).status_code == 404


async def test_a_refused_product_is_nowhere_to_be_seen(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    shop = await a_live_shop(api_client, session, "cups")
    product_id = await a_product(api_client, session, shop)
    switch(api_client, shop.moderator)
    await api_client.post(
        f"{PRODUCT_MODERATION}/{product_id}/reject",
        json={"reason": "Фото не соответствует товару"},
        headers=csrf_headers(api_client),
    )
    await anonymous(api_client)

    assert (await api_client.get(CATALOG_PRODUCTS)).json()["total"] == 0
    assert (await api_client.get(f"{CATALOG_PRODUCTS}/{product_id}")).status_code == 404


async def test_a_hidden_product_is_nowhere_to_be_seen(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    """Hiding is what a moderator does to something already on the shelf — it must leave."""
    shop = await a_live_shop(api_client, session, "cups")
    product_id = await a_published_product(api_client, session, shop)
    switch(api_client, shop.moderator)
    await api_client.post(
        f"{PRODUCT_MODERATION}/{product_id}/hide", headers=csrf_headers(api_client)
    )
    await anonymous(api_client)

    assert (await api_client.get(CATALOG_PRODUCTS)).json()["total"] == 0
    assert (await api_client.get(f"{CATALOG_PRODUCTS}/{product_id}")).status_code == 404


async def test_an_archived_product_is_nowhere_to_be_seen(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    shop = await a_live_shop(api_client, session, "cups")
    product_id = await a_published_product(api_client, session, shop)
    switch(api_client, shop.seller)
    await api_client.delete(f"{PRODUCTS_URL}/{product_id}", headers=csrf_headers(api_client))
    await anonymous(api_client)

    assert (await api_client.get(CATALOG_PRODUCTS)).json()["total"] == 0
    assert (await api_client.get(f"{CATALOG_PRODUCTS}/{product_id}")).status_code == 404


@pytest.mark.parametrize("action", ["suspend", "block"])
async def test_a_shop_taken_off_the_air_takes_its_products_with_it(
    api_client: AsyncClient, session: AsyncSession, action: str
) -> None:
    shop = await a_live_shop(api_client, session, "cups")
    product_id = await a_published_product(api_client, session, shop)
    switch(api_client, shop.moderator)
    stopped = await api_client.post(
        f"{BUSINESS_MODERATION}/{shop.business_id}/{action}",
        json={"reason": "Документы не подтверждены"},
        headers=csrf_headers(api_client),
    )
    assert stopped.status_code == 200
    await anonymous(api_client)

    assert (await api_client.get(CATALOG_PRODUCTS)).json()["total"] == 0
    assert (await api_client.get(f"{CATALOG_PRODUCTS}/{product_id}")).status_code == 404
    assert (await api_client.get(CATALOG_STORES)).json()["total"] == 0


async def test_a_seller_without_a_storefront_is_not_in_the_catalogue(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    """A product with no shop window to link to has nowhere to be shown."""
    registered = await register_seller(api_client, email=f"seller-{uuid.uuid4().hex}@example.com")
    business_id = registered.json()["business"]["id"]
    category = await seeded_category(session)
    created = await create_product(api_client, category.id)
    seller = dict(api_client.cookies)
    await become_moderator(api_client, session)
    await api_client.post(
        f"{BUSINESS_MODERATION}/{business_id}/approve", headers=csrf_headers(api_client)
    )
    await api_client.post(
        f"{PRODUCT_MODERATION}/{created.json()['id']}/approve", headers=csrf_headers(api_client)
    )
    del seller
    await anonymous(api_client)

    assert (await api_client.get(CATALOG_PRODUCTS)).json()["total"] == 0


async def test_search_looks_in_the_name_and_in_the_description(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    shop = await a_live_shop(api_client, session, "cups")
    await a_published_product(api_client, session, shop, name="Кружка керамическая")
    await a_published_product(
        api_client, session, shop, name="Тарелка", description="Керамика ручной работы"
    )
    await a_published_product(api_client, session, shop, name="Чайник")
    await anonymous(api_client)

    by_name = await api_client.get(CATALOG_PRODUCTS, params={"q": "кружка"})
    by_description = await api_client.get(CATALOG_PRODUCTS, params={"q": "ручной"})
    by_part_of_a_word = await api_client.get(CATALOG_PRODUCTS, params={"q": "керам"})

    assert [item["name"] for item in by_name.json()["items"]] == ["Кружка керамическая"]
    assert [item["name"] for item in by_description.json()["items"]] == ["Тарелка"]
    assert by_part_of_a_word.json()["total"] == 2


async def test_search_finds_nothing_when_there_is_nothing(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    shop = await a_live_shop(api_client, session, "cups")
    await a_published_product(api_client, session, shop, name="Кружка")
    await anonymous(api_client)

    response = await api_client.get(CATALOG_PRODUCTS, params={"q": "велосипед"})

    assert response.json() == {"items": [], "total": 0, "limit": 24, "offset": 0}


@pytest.mark.parametrize("query", ["%", "_", "%%", "\\"])
async def test_a_wildcard_in_the_query_does_not_widen_the_search(
    api_client: AsyncClient, session: AsyncSession, query: str
) -> None:
    """Otherwise a single % would return the whole catalogue."""
    shop = await a_live_shop(api_client, session, "cups")
    await a_published_product(api_client, session, shop, name="Кружка")
    await anonymous(api_client)

    response = await api_client.get(CATALOG_PRODUCTS, params={"q": query})

    assert response.json()["total"] == 0


async def test_search_does_not_reach_an_unpublished_product(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    shop = await a_live_shop(api_client, session, "cups")
    await a_product(api_client, session, shop, name="Секретная кружка")
    await anonymous(api_client)

    assert (await api_client.get(CATALOG_PRODUCTS, params={"q": "секретная"})).json()["total"] == 0


async def test_a_category_filter_narrows_the_catalogue(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    shop = await a_live_shop(api_client, session, "cups")
    await a_published_product(
        api_client, session, shop, category_slug="smartphones", name="Телефон"
    )
    await a_published_product(api_client, session, shop, category_slug="furniture", name="Стул")
    await anonymous(api_client)

    response = await api_client.get(CATALOG_PRODUCTS, params={"category": "furniture"})

    assert [item["name"] for item in response.json()["items"]] == ["Стул"]


async def test_a_top_level_category_stands_for_everything_under_it(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    shop = await a_live_shop(api_client, session, "cups")
    await a_published_product(
        api_client, session, shop, category_slug="smartphones", name="Телефон"
    )
    await a_published_product(api_client, session, shop, category_slug="computers", name="Ноутбук")
    await a_published_product(api_client, session, shop, category_slug="furniture", name="Стул")
    await anonymous(api_client)

    response = await api_client.get(CATALOG_PRODUCTS, params={"category": "electronics"})

    assert response.json()["total"] == 2


async def test_an_unknown_category_is_not_found(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    await anonymous(api_client)

    response = await api_client.get(CATALOG_PRODUCTS, params={"category": "no-such-category"})

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "category_not_found"


async def test_the_catalogue_can_be_narrowed_to_one_shop(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    first = await a_live_shop(api_client, session, "cups")
    await a_published_product(api_client, session, first, name="Кружка")
    second = await a_live_shop(api_client, session, "mugs")
    await a_published_product(api_client, session, second, name="Чайник")
    await anonymous(api_client)

    response = await api_client.get(CATALOG_PRODUCTS, params={"store": "mugs"})

    assert [item["name"] for item in response.json()["items"]] == ["Чайник"]


async def test_the_catalogue_is_paginated(api_client: AsyncClient, session: AsyncSession) -> None:
    shop = await a_live_shop(api_client, session, "cups")
    for index in range(3):
        await a_published_product(api_client, session, shop, name=f"Товар {index}")
    await anonymous(api_client)

    response = await api_client.get(CATALOG_PRODUCTS, params={"limit": 2, "offset": 2})

    body = response.json()
    assert body["total"] == 3
    assert len(body["items"]) == 1


@pytest.mark.parametrize(
    "params",
    [{"limit": 0}, {"limit": 101}, {"offset": -1}, {"q": ""}, {"q": "к" * 101}],
)
async def test_malformed_query_parameters_are_refused(
    api_client: AsyncClient, params: dict[str, Any]
) -> None:
    assert (await api_client.get(CATALOG_PRODUCTS, params=params)).status_code == 422


async def test_the_shop_list_holds_shops_on_the_air(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    await a_live_shop(api_client, session, "cups")
    await anonymous(api_client)

    response = await api_client.get(CATALOG_STORES)

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    item = body["items"][0]
    assert item["subdomain"] == "cups"
    assert set(item) == {
        "subdomain",
        "display_name",
        "description",
        "logo_url",
        "banner_url",
        "contacts",
    }


async def test_a_draft_shop_is_not_listed(api_client: AsyncClient, session: AsyncSession) -> None:
    await register_seller(api_client, email=f"seller-{uuid.uuid4().hex}@example.com")
    await api_client.post(STORES_URL, json={"subdomain": "cups"}, headers=csrf_headers(api_client))
    await anonymous(api_client)

    assert (await api_client.get(CATALOG_STORES)).json()["total"] == 0


async def test_the_category_tree_is_offered_to_the_visitor(api_client: AsyncClient) -> None:
    response = await api_client.get(CATALOG_CATEGORIES)

    assert response.status_code == 200
    tree = response.json()
    assert len(tree) >= 8
    electronics = next(root for root in tree if root["slug"] == "electronics")
    assert "smartphones" in {child["slug"] for child in electronics["children"]}
    # the id comes with it: a seller files a product under a category by id, not by slug
    assert set(electronics) == {"id", "slug", "name", "children"}
    assert uuid.UUID(electronics["children"][0]["id"])
