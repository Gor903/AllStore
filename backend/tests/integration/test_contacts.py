import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Business
from tests.integration.conftest import (
    CONTACTS_URL,
    PRODUCTS_URL,
    create_product,
    csrf_headers,
    product_payload,
    register_buyer,
    register_seller,
    seeded_category,
    set_contacts,
)
from tests.integration.test_catalog import (
    CATALOG_PRODUCTS,
    CATALOG_STORES,
    Shop,
    a_live_shop,
    a_published_product,
    anonymous,
    switch,
)

pytestmark = pytest.mark.integration

STOREFRONT_URL = "/api/v1/storefront"
PHONE = {"platform": "phone", "value": "+37410123456"}


async def a_seller(client: AsyncClient) -> None:
    client.cookies.clear()
    await register_seller(client, email=f"seller-{uuid.uuid4().hex}@example.com")


async def contacts_of(client: AsyncClient) -> list[dict[str, str]]:
    response = await client.get(CONTACTS_URL)
    assert response.status_code == 200
    items: list[dict[str, str]] = response.json()["items"]
    return items


async def test_a_seller_sets_and_reads_back_their_contacts(api_client: AsyncClient) -> None:
    await a_seller(api_client)

    saved = await set_contacts(api_client, PHONE, {"platform": "telegram", "value": "@mystore"})

    assert saved.status_code == 200
    assert await contacts_of(api_client) == [
        {"platform": "phone", "value": "+37410123456", "href": "tel:+37410123456"},
        {"platform": "telegram", "value": "mystore", "href": "https://t.me/mystore"},
    ]


async def test_a_contact_left_out_of_the_set_is_gone(api_client: AsyncClient) -> None:
    """The form is replaced whole, so clearing a field clears the contact behind it."""
    await a_seller(api_client)
    await set_contacts(api_client, PHONE, {"platform": "viber", "value": "+37410123456"})

    await set_contacts(api_client, PHONE)

    assert [item["platform"] for item in await contacts_of(api_client)] == ["phone"]


async def test_the_set_may_be_emptied(api_client: AsyncClient) -> None:
    await a_seller(api_client)
    await set_contacts(api_client, PHONE)

    response = await api_client.put(
        CONTACTS_URL, json={"items": []}, headers=csrf_headers(api_client)
    )

    assert response.status_code == 200
    assert await contacts_of(api_client) == []


async def test_one_platform_cannot_be_listed_twice(api_client: AsyncClient) -> None:
    await a_seller(api_client)

    response = await set_contacts(api_client, PHONE, {"platform": "phone", "value": "+37411222333"})

    assert response.status_code == 422
    assert "Телефон" in response.text


@pytest.mark.parametrize(
    ("written", "stored"),
    [
        ("+374 10 123-456", "+37410123456"),
        ("+374 (10) 123456", "+37410123456"),
        # the international prefix as it is dialled from a landline
        ("0037410123456", "+37410123456"),
    ],
)
async def test_a_phone_is_stored_in_one_shape(
    api_client: AsyncClient, written: str, stored: str
) -> None:
    await a_seller(api_client)

    await set_contacts(api_client, {"platform": "phone", "value": written})

    assert (await contacts_of(api_client))[0]["value"] == stored


@pytest.mark.parametrize(
    "written",
    ["10123456", "+0374101234", "не телефон", "+374", "+3741012345678901234"],
)
async def test_a_number_that_cannot_be_dialled_is_rejected(
    api_client: AsyncClient, written: str
) -> None:
    await a_seller(api_client)

    response = await set_contacts(api_client, {"platform": "phone", "value": written})

    assert response.status_code == 422
    assert await contacts_of(api_client) == []


@pytest.mark.parametrize(
    ("platform", "written", "stored"),
    [
        ("telegram", "https://t.me/mystore", "mystore"),
        ("telegram", "t.me/mystore", "mystore"),
        ("telegram", "@mystore", "mystore"),
        ("instagram", "https://www.instagram.com/my.store/", "my.store"),
        ("instagram", "https://instagram.com/my.store?igshid=abc", "my.store"),
        ("facebook", "https://facebook.com/my.store", "my.store"),
    ],
)
async def test_a_pasted_profile_link_becomes_a_handle(
    api_client: AsyncClient, platform: str, written: str, stored: str
) -> None:
    """A seller pastes what the app gave them — the link is as common as the handle."""
    await a_seller(api_client)

    await set_contacts(api_client, {"platform": platform, "value": written})

    assert (await contacts_of(api_client))[0]["value"] == stored


@pytest.mark.parametrize(
    ("platform", "written"),
    [
        ("telegram", "me"),
        ("telegram", "my store"),
        ("instagram", "https://vk.com/mystore"),
        ("facebook", "a/b"),
    ],
)
async def test_a_handle_that_is_not_one_is_rejected(
    api_client: AsyncClient, platform: str, written: str
) -> None:
    await a_seller(api_client)

    response = await set_contacts(api_client, {"platform": platform, "value": written})

    assert response.status_code == 422
    assert await contacts_of(api_client) == []


async def test_every_platform_carries_the_address_a_browser_can_open(
    api_client: AsyncClient,
) -> None:
    await a_seller(api_client)

    await set_contacts(
        api_client,
        PHONE,
        {"platform": "whatsapp", "value": "+37410123456"},
        {"platform": "telegram", "value": "mystore"},
        {"platform": "viber", "value": "+37410123456"},
        {"platform": "instagram", "value": "mystore"},
        {"platform": "facebook", "value": "my.store"},
    )

    assert {item["platform"]: item["href"] for item in await contacts_of(api_client)} == {
        "phone": "tel:+37410123456",
        # wa.me takes the number without the plus
        "whatsapp": "https://wa.me/37410123456",
        "telegram": "https://t.me/mystore",
        "viber": "viber://chat?number=%2B37410123456",
        "instagram": "https://instagram.com/mystore",
        "facebook": "https://facebook.com/my.store",
    }


async def test_a_seller_does_not_touch_the_contacts_of_another(api_client: AsyncClient) -> None:
    await a_seller(api_client)
    await set_contacts(api_client, PHONE)
    first = dict(api_client.cookies)

    await a_seller(api_client)
    await set_contacts(api_client, {"platform": "telegram", "value": "second"})

    assert [item["platform"] for item in await contacts_of(api_client)] == ["telegram"]
    switch(api_client, first)
    assert [item["value"] for item in await contacts_of(api_client)] == ["+37410123456"]


async def test_a_seller_without_a_business_gets_404(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    await a_seller(api_client)
    await session.execute(delete(Business))
    await session.flush()

    assert (await api_client.get(CONTACTS_URL)).status_code == 404
    assert (await set_contacts(api_client, PHONE)).status_code == 404


async def test_a_buyer_has_no_contacts_to_set(api_client: AsyncClient) -> None:
    await register_buyer(api_client)

    response = await set_contacts(api_client, PHONE)

    assert response.status_code == 403


async def test_an_anonymous_visitor_cannot_set_contacts(api_client: AsyncClient) -> None:
    """403, not 401: the CSRF gate answers before authentication, as everywhere else here."""
    response = await api_client.put(CONTACTS_URL, json={"items": [PHONE]})

    assert response.status_code == 403
    assert (await api_client.get(CONTACTS_URL)).status_code == 401


async def test_setting_contacts_without_the_csrf_header_is_forbidden(
    api_client: AsyncClient,
) -> None:
    await a_seller(api_client)

    response = await api_client.put(CONTACTS_URL, json={"items": [PHONE]})

    assert response.status_code == 403


async def test_a_product_needs_a_contact_before_it_enters_the_queue(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    """Creating a product files it straight into the queue, so the rule is checked here."""
    await a_seller(api_client)
    category = await seeded_category(session)

    response = await api_client.post(
        PRODUCTS_URL, json=product_payload(category.id), headers=csrf_headers(api_client)
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "contacts_required"


async def test_a_product_is_created_once_a_contact_exists(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    await a_seller(api_client)
    category = await seeded_category(session)
    await set_contacts(api_client, PHONE)

    response = await api_client.post(
        PRODUCTS_URL, json=product_payload(category.id), headers=csrf_headers(api_client)
    )

    assert response.status_code == 201


async def test_a_product_is_not_resubmitted_after_the_last_contact_is_cleared(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    await a_seller(api_client)
    category = await seeded_category(session)
    product_id = (await create_product(api_client, category.id)).json()["id"]
    await api_client.put(CONTACTS_URL, json={"items": []}, headers=csrf_headers(api_client))

    response = await api_client.post(
        f"{PRODUCTS_URL}/{product_id}/submit", headers=csrf_headers(api_client)
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "contacts_required"


async def test_a_buyer_sees_the_contacts_on_the_storefront(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    shop = await a_live_shop(api_client, session, "cups")
    switch(api_client, shop.seller)
    await set_contacts(api_client, PHONE, {"platform": "whatsapp", "value": "+37410123456"})
    await anonymous(api_client)

    body = (await api_client.get(f"{STOREFRONT_URL}/cups")).json()

    assert [item["platform"] for item in body["contacts"]] == ["phone", "whatsapp"]
    assert body["contacts"][0]["href"] == "tel:+37410123456"


async def test_a_buyer_sees_the_contacts_on_the_product_card(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    shop = await a_live_shop(api_client, session, "cups")
    product_id = await a_published_product(api_client, session, shop)
    switch(api_client, shop.seller)
    await set_contacts(api_client, PHONE)
    await anonymous(api_client)

    body = (await api_client.get(f"{CATALOG_PRODUCTS}/{product_id}")).json()

    assert body["store"]["contacts"] == [
        {"platform": "phone", "value": "+37410123456", "href": "tel:+37410123456"}
    ]


async def test_the_listing_carries_no_contacts(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    """Twenty products of one shop would repeat the same phone twenty times."""
    shop = await a_live_shop(api_client, session, "cups")
    await a_published_product(api_client, session, shop)
    await anonymous(api_client)

    item = (await api_client.get(CATALOG_PRODUCTS)).json()["items"][0]

    assert set(item["store"]) == {"subdomain", "display_name"}


async def test_nothing_of_the_account_leaks_into_the_contacts(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    """Only what the seller entered is shown: not the login email, not the phone of the
    user record, not the legal name — none of those is a contact by itself."""
    shop = await a_live_shop(api_client, session, "cups")
    switch(api_client, shop.seller)
    await set_contacts(api_client, PHONE)
    await anonymous(api_client)

    body = (await api_client.get(f"{STOREFRONT_URL}/cups")).json()

    assert {item["value"] for item in body["contacts"]} == {"+37410123456"}
    assert "seller-" not in str(body)
    assert 'ИП "Тестовый"' not in str(body)


async def test_a_published_product_keeps_its_place_when_the_contacts_go(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    """The rule guards the way into the queue, not the shelf: a product published before
    the rule existed stays where it is (решение владельца продукта, 2026-09-22)."""
    shop = await a_live_shop(api_client, session, "cups")
    await a_published_product(api_client, session, shop)
    switch(api_client, shop.seller)
    await api_client.put(CONTACTS_URL, json={"items": []}, headers=csrf_headers(api_client))
    await anonymous(api_client)

    listed = (await api_client.get(CATALOG_PRODUCTS)).json()

    assert listed["total"] == 1
    assert listed["items"][0]["store"]["subdomain"] == "cups"


async def test_a_shop_without_contacts_still_answers(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    shop: Shop = await a_live_shop(api_client, session, "cups")
    await anonymous(api_client)

    body = (await api_client.get(CATALOG_STORES)).json()

    assert body["items"][0]["contacts"] == []
    assert shop.subdomain == body["items"][0]["subdomain"]
