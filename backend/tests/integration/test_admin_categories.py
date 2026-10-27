import uuid
from typing import Any

import pytest
from httpx import AsyncClient, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import UserRole
from tests.integration.conftest import act_as, csrf_headers, seed_staff, seeded_category
from tests.integration.test_admin_users import entries

pytestmark = pytest.mark.integration

ADMIN_CATEGORIES = "/api/v1/admin/categories"
PUBLIC_CATEGORIES = "/api/v1/catalog/categories"


async def as_admin(client: AsyncClient, session: AsyncSession) -> None:
    await act_as(client, await seed_staff(session, UserRole.ADMIN))


async def create(client: AsyncClient, **body: object) -> Response:
    return await client.post(ADMIN_CATEGORIES, json=body, headers=csrf_headers(client))


async def patch(client: AsyncClient, category_id: str, **body: object) -> Response:
    return await client.patch(
        f"{ADMIN_CATEGORIES}/{category_id}", json=body, headers=csrf_headers(client)
    )


def slugs_of(tree: list[dict[str, Any]]) -> set[str]:
    found: set[str] = set()
    for root in tree:
        found.add(str(root["slug"]))
        for child in root["children"]:
            found.add(str(child["slug"]))
    return found


async def test_an_admin_adds_a_top_level_category(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    """Until now the reference book arrived by migration: a new category meant a deploy."""
    await as_admin(api_client, session)

    response = await create(api_client, name="Зоотовары", slug="pets")

    assert response.status_code == 201
    assert response.json()["slug"] == "pets"
    assert response.json()["status"] == "active"
    assert "pets" in slugs_of((await api_client.get(ADMIN_CATEGORIES)).json())


async def test_a_subcategory_is_filed_under_its_parent(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    await as_admin(api_client, session)
    parent = (await create(api_client, name="Зоотовары", slug="pets")).json()

    child = await create(api_client, name="Корм", slug="pet-food", parent_id=parent["id"])

    assert child.status_code == 201
    tree = (await api_client.get(ADMIN_CATEGORIES)).json()
    branch = next(root for root in tree if root["slug"] == "pets")
    assert [item["slug"] for item in branch["children"]] == ["pet-food"]


async def test_the_tree_stays_two_levels_deep(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    await as_admin(api_client, session)
    parent = (await create(api_client, name="Зоотовары", slug="pets")).json()
    child = (await create(api_client, name="Корм", slug="pet-food", parent_id=parent["id"])).json()

    response = await create(api_client, name="Сухой", slug="dry-food", parent_id=child["id"])

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "category_tree_too_deep"


async def test_a_taken_address_is_refused(api_client: AsyncClient, session: AsyncSession) -> None:
    await as_admin(api_client, session)
    existing = await seeded_category(session)

    response = await create(api_client, name="Другое имя", slug=existing.slug)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "category_slug_taken"


@pytest.mark.parametrize(
    "slug", ["Электроника", "with space", "trailing-", "-leading", "двойной--дефис"]
)
async def test_an_address_that_is_not_url_safe_is_refused(
    api_client: AsyncClient, session: AsyncSession, slug: str
) -> None:
    await as_admin(api_client, session)

    assert (await create(api_client, name="Категория", slug=slug)).status_code == 422


async def test_an_address_is_stored_in_lower_case(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    await as_admin(api_client, session)

    response = await create(api_client, name="Зоотовары", slug="PETS")

    assert response.json()["slug"] == "pets"


async def test_a_category_is_renamed(api_client: AsyncClient, session: AsyncSession) -> None:
    await as_admin(api_client, session)
    category = await seeded_category(session)

    response = await patch(api_client, str(category.id), name="Электроника и техника")

    assert response.status_code == 200
    assert response.json()["name"] == "Электроника и техника"
    # the address does not follow the name: it is a link a visitor may have saved
    assert response.json()["slug"] == category.slug


async def test_the_address_cannot_be_edited(api_client: AsyncClient, session: AsyncSession) -> None:
    await as_admin(api_client, session)
    category = await seeded_category(session)

    response = await patch(api_client, str(category.id), slug="new-slug")

    assert response.status_code == 422


async def test_a_hidden_category_leaves_the_public_tree(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    await as_admin(api_client, session)
    category = await seeded_category(session)

    await patch(api_client, str(category.id), status="hidden")

    public = (await api_client.get(PUBLIC_CATEGORIES)).json()
    assert category.slug not in slugs_of(public)
    # the administrator still sees it, that is the point of hiding rather than deleting
    assert category.slug in slugs_of((await api_client.get(ADMIN_CATEGORIES)).json())


async def test_a_hidden_subcategory_leaves_the_public_tree_too(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    """A hidden child used to stay in its parent's listing: the filter still offered it."""
    await as_admin(api_client, session)
    child = await seeded_category(session, "smartphones")

    await patch(api_client, str(child.id), status="hidden")

    assert "smartphones" not in slugs_of((await api_client.get(PUBLIC_CATEGORIES)).json())


async def test_a_hidden_category_comes_back(api_client: AsyncClient, session: AsyncSession) -> None:
    await as_admin(api_client, session)
    category = await seeded_category(session)
    await patch(api_client, str(category.id), status="hidden")

    await patch(api_client, str(category.id), status="active")

    assert category.slug in slugs_of((await api_client.get(PUBLIC_CATEGORIES)).json())


async def test_a_hidden_category_takes_no_new_products(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    """Hiding keeps the products already filed under it; it stops new ones arriving."""
    await as_admin(api_client, session)
    category = await seeded_category(session, "smartphones")
    await patch(api_client, str(category.id), status="hidden")

    from tests.integration.conftest import create_product, register_seller

    api_client.cookies.clear()
    await register_seller(api_client, email=f"seller-{uuid.uuid4().hex}@example.com")
    response = await create_product(api_client, category.id)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "category_not_found"


async def test_a_missing_category_answers_404(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    await as_admin(api_client, session)

    response = await patch(api_client, str(uuid.uuid4()), name="Неважно")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "category_not_found"


async def test_every_change_leaves_a_record(api_client: AsyncClient, session: AsyncSession) -> None:
    await as_admin(api_client, session)
    created = (await create(api_client, name="Зоотовары", slug="pets")).json()
    await patch(api_client, created["id"], name="Товары для животных")
    await patch(api_client, created["id"], status="hidden")
    await patch(api_client, created["id"], status="active")

    written = await entries(session)
    assert [entry.action for entry in written] == [
        "category.created",
        "category.renamed",
        "category.hidden",
        "category.shown",
    ]
    assert written[1].details == {"from": "Зоотовары", "to": "Товары для животных"}


async def test_an_unchanged_category_leaves_no_record(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    await as_admin(api_client, session)
    category = await seeded_category(session)

    await patch(api_client, str(category.id), name=category.name, status="active")

    assert await entries(session) == []


@pytest.mark.parametrize("role", [UserRole.MODERATOR, UserRole.BUYER])
async def test_only_an_administrator_manages_the_reference_book(
    api_client: AsyncClient, session: AsyncSession, role: UserRole
) -> None:
    category = await seeded_category(session)
    await act_as(api_client, await seed_staff(session, role))

    assert (await api_client.get(ADMIN_CATEGORIES)).status_code == 403
    assert (await create(api_client, name="Зоотовары", slug="pets")).status_code == 403
    assert (await patch(api_client, str(category.id), name="Иначе")).status_code == 403


async def test_creating_a_category_without_the_csrf_header_is_forbidden(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    await as_admin(api_client, session)

    response = await api_client.post(ADMIN_CATEGORIES, json={"name": "Зоотовары", "slug": "pets"})

    assert response.status_code == 403
