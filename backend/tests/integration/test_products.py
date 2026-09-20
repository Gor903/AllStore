import uuid
from typing import Any

import pytest
from httpx import AsyncClient, Response
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Business, Category, CategoryStatus, ModerationStatus, Product
from tests.integration.conftest import csrf_headers, register_buyer, register_seller

pytestmark = pytest.mark.integration

PRODUCTS_URL = "/api/v1/products"


async def seeded_category(session: AsyncSession, slug: str = "electronics") -> Category:
    """The starting catalogue comes from migration 0004, committed outside the test transaction."""
    result = await session.execute(select(Category).where(Category.slug == slug))
    return result.scalar_one()


def product_payload(category_id: uuid.UUID, **overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "category_id": str(category_id),
        "name": "Кружка керамическая",
        "price": "1500.00",
    }
    body.update(overrides)
    return body


async def create_product(client: AsyncClient, category_id: uuid.UUID, **overrides: Any) -> Response:
    return await client.post(
        PRODUCTS_URL, json=product_payload(category_id, **overrides), headers=csrf_headers(client)
    )


async def register_second_seller(client: AsyncClient) -> None:
    """A seller registration replaces the cookies, so the client acts as the new account."""
    client.cookies.clear()
    await register_seller(client, email=f"seller-{uuid.uuid4().hex}@example.com")


async def approve(session: AsyncSession, product_id: str) -> None:
    """Moderation itself lands in этап 5; here the verdict is set straight in the database."""
    product = await session.get(Product, uuid.UUID(product_id))
    assert product is not None
    product.moderation_status = ModerationStatus.APPROVED
    await session.flush()


async def test_seller_creates_a_product(api_client: AsyncClient, session: AsyncSession) -> None:
    await register_seller(api_client)
    category = await seeded_category(session)

    response = await create_product(api_client, category.id)

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Кружка керамическая"
    assert body["price"] == "1500.00"
    assert body["currency"] == "AMD"
    assert body["stock_quantity"] == 0
    assert body["availability_status"] == "in_stock"


async def test_new_product_waits_for_moderation_and_is_not_published(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    await register_seller(api_client)
    category = await seeded_category(session)

    body = (await create_product(api_client, category.id)).json()

    assert body["moderation_status"] == "pending"
    assert body["publication_status"] == "draft"


async def test_name_is_trimmed(api_client: AsyncClient, session: AsyncSession) -> None:
    await register_seller(api_client)
    category = await seeded_category(session)

    response = await create_product(api_client, category.id, name="  Кружка  ")

    assert response.json()["name"] == "Кружка"


@pytest.mark.parametrize("missing", ["name", "price", "category_id"])
async def test_a_required_field_cannot_be_missing(
    api_client: AsyncClient, session: AsyncSession, missing: str
) -> None:
    await register_seller(api_client)
    category = await seeded_category(session)
    body = product_payload(category.id)
    del body[missing]

    response = await api_client.post(PRODUCTS_URL, json=body, headers=csrf_headers(api_client))

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_failed"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("name", "   "),  # whitespace is not a name
        ("name", "к" * 256),  # longer than the column
        ("price", "-1.00"),  # negative
        ("price", "10.999"),  # more than two decimal places
        ("price", "не число"),
        ("stock_quantity", -1),
        ("availability_status", "maybe"),
        ("category_id", "не uuid"),
    ],
)
async def test_malformed_values_are_rejected_by_the_backend(
    api_client: AsyncClient, session: AsyncSession, field: str, value: Any
) -> None:
    await register_seller(api_client)
    category = await seeded_category(session)
    body = product_payload(category.id)
    body[field] = value

    response = await api_client.post(PRODUCTS_URL, json=body, headers=csrf_headers(api_client))

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_failed"


async def test_an_unknown_category_is_rejected(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    await register_seller(api_client)
    await seeded_category(session)

    response = await create_product(api_client, uuid.uuid4())

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "category_not_found"
    assert error["details"][0]["loc"] == ["body", "category_id"]


async def test_a_hidden_category_is_rejected(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    await register_seller(api_client)
    category = await seeded_category(session)
    category.status = CategoryStatus.HIDDEN
    await session.flush()

    response = await create_product(api_client, category.id)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "category_not_found"


@pytest.mark.parametrize("field", ["moderation_status", "publication_status", "business_id"])
async def test_a_seller_cannot_set_a_field_that_is_not_theirs(
    api_client: AsyncClient, session: AsyncSession, field: str
) -> None:
    """A seller must not approve, publish or reassign their own product."""
    await register_seller(api_client)
    category = await seeded_category(session)

    response = await create_product(api_client, category.id, **{field: "approved"})

    assert response.status_code == 422


async def test_buyer_cannot_create_a_product(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    await register_buyer(api_client)
    category = await seeded_category(session)

    response = await create_product(api_client, category.id)

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "permission_denied"


async def test_anonymous_cannot_touch_products(api_client: AsyncClient) -> None:
    """403, not 401: the CSRF gate answers before authentication, as everywhere else."""
    assert (await api_client.post(PRODUCTS_URL, json={})).status_code == 403
    assert (await api_client.get(PRODUCTS_URL)).status_code == 401


async def test_a_seller_without_a_business_gets_404(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    await register_seller(api_client)
    category = await seeded_category(session)
    await session.execute(delete(Business))
    await session.flush()

    assert (await create_product(api_client, category.id)).status_code == 404
    assert (await api_client.get(PRODUCTS_URL)).status_code == 404


async def test_the_list_holds_only_the_sellers_own_products(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    await register_seller(api_client)
    category = await seeded_category(session)
    assert (await create_product(api_client, category.id, name="Мой товар")).status_code == 201
    await register_second_seller(api_client)
    await create_product(api_client, category.id, name="Чужой товар")

    response = await api_client.get(PRODUCTS_URL)

    body = response.json()
    assert body["total"] == 1
    assert [item["name"] for item in body["items"]] == ["Чужой товар"]


async def test_the_list_is_paginated(api_client: AsyncClient, session: AsyncSession) -> None:
    await register_seller(api_client)
    category = await seeded_category(session)
    for index in range(3):
        assert (
            await create_product(api_client, category.id, name=f"Товар {index}")
        ).status_code == 201

    response = await api_client.get(PRODUCTS_URL, params={"limit": 2, "offset": 2})

    body = response.json()
    assert body["total"] == 3
    assert len(body["items"]) == 1
    assert body["limit"] == 2
    assert body["offset"] == 2


@pytest.mark.parametrize(("limit", "offset"), [(0, 0), (101, 0), (20, -1)])
async def test_malformed_pagination_is_rejected(
    api_client: AsyncClient, limit: int, offset: int
) -> None:
    await register_seller(api_client)

    response = await api_client.get(PRODUCTS_URL, params={"limit": limit, "offset": offset})

    assert response.status_code == 422


async def test_seller_reads_their_own_product(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    await register_seller(api_client)
    category = await seeded_category(session)
    created = (await create_product(api_client, category.id)).json()

    response = await api_client.get(f"{PRODUCTS_URL}/{created['id']}")

    assert response.status_code == 200
    assert response.json()["id"] == created["id"]


async def test_a_foreign_product_is_not_readable(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    """404 rather than 403 — a seller must not learn that someone else's product exists."""
    await register_seller(api_client)
    category = await seeded_category(session)
    created = (await create_product(api_client, category.id)).json()
    await register_second_seller(api_client)

    response = await api_client.get(f"{PRODUCTS_URL}/{created['id']}")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "product_not_found"


async def test_seller_edits_their_own_product(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    await register_seller(api_client)
    category = await seeded_category(session)
    created = (await create_product(api_client, category.id)).json()

    response = await api_client.patch(
        f"{PRODUCTS_URL}/{created['id']}",
        json={"name": "Кружка большая", "price": "1800.50", "stock_quantity": 7},
        headers=csrf_headers(api_client),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Кружка большая"
    assert body["price"] == "1800.50"
    assert body["stock_quantity"] == 7


async def test_a_product_moves_between_categories(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    await register_seller(api_client)
    created = (await create_product(api_client, (await seeded_category(session)).id)).json()
    target = await seeded_category(session, slug="furniture")

    response = await api_client.patch(
        f"{PRODUCTS_URL}/{created['id']}",
        json={"category_id": str(target.id)},
        headers=csrf_headers(api_client),
    )

    assert response.status_code == 200
    assert response.json()["category_id"] == str(target.id)


async def test_a_product_cannot_move_into_an_unknown_category(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    await register_seller(api_client)
    created = (await create_product(api_client, (await seeded_category(session)).id)).json()

    response = await api_client.patch(
        f"{PRODUCTS_URL}/{created['id']}",
        json={"category_id": str(uuid.uuid4())},
        headers=csrf_headers(api_client),
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "category_not_found"


async def test_a_foreign_product_cannot_be_edited(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    await register_seller(api_client)
    category = await seeded_category(session)
    created = (await create_product(api_client, category.id)).json()
    await register_second_seller(api_client)

    response = await api_client.patch(
        f"{PRODUCTS_URL}/{created['id']}",
        json={"name": "Захвачено"},
        headers=csrf_headers(api_client),
    )

    assert response.status_code == 404
    unchanged = await session.get(Product, uuid.UUID(created["id"]))
    assert unchanged is not None
    assert unchanged.name == "Кружка керамическая"


async def test_a_foreign_product_cannot_be_archived(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    await register_seller(api_client)
    category = await seeded_category(session)
    created = (await create_product(api_client, category.id)).json()
    await register_second_seller(api_client)

    response = await api_client.delete(
        f"{PRODUCTS_URL}/{created['id']}", headers=csrf_headers(api_client)
    )

    assert response.status_code == 404
    survivor = await session.get(Product, uuid.UUID(created["id"]))
    assert survivor is not None
    assert survivor.archived_at is None


async def test_a_seller_cannot_file_a_product_into_a_foreign_business(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    """The tenant key comes from the session; a body cannot redirect it."""
    await register_seller(api_client)
    category = await seeded_category(session)
    first = (await session.execute(select(Business))).scalars().one()
    await register_second_seller(api_client)

    created = await create_product(api_client, category.id)

    assert created.json()["business_id"] != str(first.id)


async def test_only_the_description_may_be_cleared(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    await register_seller(api_client)
    category = await seeded_category(session)
    created = (await create_product(api_client, category.id, description="Была")).json()
    url = f"{PRODUCTS_URL}/{created['id']}"

    cleared = await api_client.patch(
        url, json={"description": None}, headers=csrf_headers(api_client)
    )
    nulled_name = await api_client.patch(url, json={"name": None}, headers=csrf_headers(api_client))

    assert cleared.status_code == 200
    assert cleared.json()["description"] is None
    assert nulled_name.status_code == 422


async def test_editing_what_was_approved_sends_the_product_back_to_moderation(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    await register_seller(api_client)
    category = await seeded_category(session)
    created = (await create_product(api_client, category.id)).json()
    await approve(session, created["id"])

    response = await api_client.patch(
        f"{PRODUCTS_URL}/{created['id']}",
        json={"name": "Совсем другой товар"},
        headers=csrf_headers(api_client),
    )

    assert response.json()["moderation_status"] == "pending"
    assert response.json()["publication_status"] == "draft"


async def test_changing_the_price_keeps_the_approval(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    """A price is not what a moderator judged, so re-pricing must not restart the queue."""
    await register_seller(api_client)
    category = await seeded_category(session)
    created = (await create_product(api_client, category.id)).json()
    await approve(session, created["id"])

    response = await api_client.patch(
        f"{PRODUCTS_URL}/{created['id']}",
        json={"price": "1600.00", "stock_quantity": 3},
        headers=csrf_headers(api_client),
    )

    assert response.json()["moderation_status"] == "approved"


async def test_an_archived_product_leaves_the_catalogue_of_the_seller(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    await register_seller(api_client)
    category = await seeded_category(session)
    created = (await create_product(api_client, category.id)).json()

    archived = await api_client.delete(
        f"{PRODUCTS_URL}/{created['id']}", headers=csrf_headers(api_client)
    )

    assert archived.status_code == 204
    assert (await api_client.get(PRODUCTS_URL)).json()["total"] == 0
    assert (await api_client.get(f"{PRODUCTS_URL}/{created['id']}")).status_code == 404
    stored = await session.get(Product, uuid.UUID(created["id"]))
    assert stored is not None
    assert stored.archived_at is not None
    # the row survives, so a moderation verdict and the images keep their subject
    assert stored.publication_status.value == "hidden"


async def test_an_archived_product_cannot_be_edited(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    await register_seller(api_client)
    category = await seeded_category(session)
    created = (await create_product(api_client, category.id)).json()
    await api_client.delete(f"{PRODUCTS_URL}/{created['id']}", headers=csrf_headers(api_client))

    response = await api_client.patch(
        f"{PRODUCTS_URL}/{created['id']}",
        json={"name": "Воскрешение"},
        headers=csrf_headers(api_client),
    )

    assert response.status_code == 404


@pytest.mark.parametrize("method", ["post", "patch", "delete"])
async def test_a_mutation_without_the_csrf_header_is_forbidden(
    api_client: AsyncClient, session: AsyncSession, method: str
) -> None:
    await register_seller(api_client)
    category = await seeded_category(session)
    created = (await create_product(api_client, category.id)).json()
    urls = {
        "post": PRODUCTS_URL,
        "patch": f"{PRODUCTS_URL}/{created['id']}",
        "delete": f"{PRODUCTS_URL}/{created['id']}",
    }

    response = await api_client.request(method.upper(), urls[method], json={"name": "Без токена"})

    assert response.status_code == 403
