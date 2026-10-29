import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models import Business, BusinessStatus, Store, StoreStatus, User, UserRole
from tests.integration.conftest import csrf_headers, register_seller

pytestmark = pytest.mark.integration

BY_HOST_URL = "/api/v1/storefront"
PUBLIC_FIELDS = {
    "subdomain",
    "display_name",
    "description",
    "logo_url",
    "banner_url",
    "primary_color",
    "secondary_color",
    "theme_id",
    "contacts",
}


async def seed_store(
    session: AsyncSession,
    subdomain: str,
    store_status: StoreStatus = StoreStatus.ACTIVE,
    business_status: BusinessStatus = BusinessStatus.ACTIVE,
) -> Store:
    """Statuses are set straight in the database: the transitions belong to moderation, этап 5."""
    user = User(
        email=f"seller-{uuid.uuid4().hex}@example.com",
        password_hash="$argon2id$fake",
        role=UserRole.SELLER,
    )
    session.add(user)
    await session.flush()
    business = Business(
        owner_user_id=user.id,
        legal_name='ИП "Секретное Название"',
        display_name="Магазин Поток",
        description="Посуда ручной работы",
        status=business_status,
    )
    session.add(business)
    await session.flush()
    store = Store(business_id=business.id, subdomain=subdomain, status=store_status)
    session.add(store)
    await session.flush()
    return store


def base_domain() -> str:
    """Read from settings, not hardcoded: BASE_DOMAIN differs between environments."""
    return get_settings().base_domain


def host(subdomain: str) -> dict[str, str]:
    return {"host": f"{subdomain}.{base_domain()}"}


async def test_storefront_resolves_from_the_host_header(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    await seed_store(session, "cups")

    response = await api_client.get(BY_HOST_URL, headers=host("cups"))

    assert response.status_code == 200
    body = response.json()
    assert body["subdomain"] == "cups"
    assert body["display_name"] == "Магазин Поток"
    assert body["description"] == "Посуда ручной работы"


async def test_storefront_exposes_public_fields_only(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    """AC 3.4: a request by subdomain must not hand out anything internal."""
    await seed_store(session, "cups")

    body = (await api_client.get(BY_HOST_URL, headers=host("cups"))).json()

    assert set(body) == PUBLIC_FIELDS
    assert "Секретное" not in str(body)


@pytest.mark.parametrize(
    ("store_status", "business_status"),
    [
        (StoreStatus.DRAFT, BusinessStatus.ACTIVE),
        (StoreStatus.SUSPENDED, BusinessStatus.ACTIVE),
        (StoreStatus.BLOCKED, BusinessStatus.ACTIVE),
        (StoreStatus.ACTIVE, BusinessStatus.PENDING),
        (StoreStatus.ACTIVE, BusinessStatus.SUSPENDED),
        (StoreStatus.ACTIVE, BusinessStatus.BLOCKED),
    ],
)
async def test_a_storefront_that_is_not_public_answers_404(
    api_client: AsyncClient,
    session: AsyncSession,
    store_status: StoreStatus,
    business_status: BusinessStatus,
) -> None:
    """Same answer as for a subdomain nobody took — the visitor learns nothing either way."""
    await seed_store(session, "cups", store_status=store_status, business_status=business_status)

    response = await api_client.get(BY_HOST_URL, headers=host("cups"))

    assert response.status_code == 404
    assert response.json()["error"]["message"] == "Магазин не найден"


@pytest.mark.parametrize(
    "template",
    [
        "unknown.{base}",  # nobody took it
        "{base}",  # the marketplace itself
        "www.{base}",  # reserved
        "api.{base}",  # reserved
        "evil.com",  # a domain we do not own
        "cups.evil.com",  # our label under someone else's domain
        "not{base}",  # ends with our name as text only
        "a.b.{base}",  # a level we do not route
        "test",  # the default host of the test client
    ],
)
async def test_hosts_that_address_no_storefront_answer_404(
    api_client: AsyncClient, session: AsyncSession, template: str
) -> None:
    await seed_store(session, "cups")

    response = await api_client.get(
        BY_HOST_URL, headers={"host": template.format(base=base_domain())}
    )

    assert response.status_code == 404


async def test_storefront_is_also_addressable_by_path(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    """Server-side rendering cannot set a Host header, so it names the subdomain instead."""
    await seed_store(session, "cups")

    response = await api_client.get(f"{BY_HOST_URL}/cups")

    assert response.status_code == 200
    assert response.json()["subdomain"] == "cups"


async def test_the_path_form_is_case_insensitive(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    await seed_store(session, "cups")

    assert (await api_client.get(f"{BY_HOST_URL}/CUPS")).status_code == 200


async def test_the_path_form_hides_a_storefront_that_is_not_public(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    await seed_store(session, "cups", store_status=StoreStatus.DRAFT)

    assert (await api_client.get(f"{BY_HOST_URL}/cups")).status_code == 404


async def test_the_path_form_rejects_a_malformed_subdomain(api_client: AsyncClient) -> None:
    response = await api_client.get(f"{BY_HOST_URL}/my_shop")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_failed"


async def test_an_unknown_subdomain_does_not_leak_through_the_path_form(
    api_client: AsyncClient,
) -> None:
    assert (await api_client.get(f"{BY_HOST_URL}/nobody-here")).status_code == 404


async def test_a_forged_host_does_not_reach_a_foreign_dashboard(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    """AC 3.3: the seller's own data is resolved from the session, never from the Host."""
    foreign = await seed_store(session, "foreign-shop")
    await register_seller(api_client, session)
    created = await api_client.post(
        "/api/v1/stores", json={"subdomain": "my-shop"}, headers=csrf_headers(api_client)
    )
    assert created.status_code == 201

    response = await api_client.get("/api/v1/stores/me", headers=host("foreign-shop"))

    assert response.status_code == 200
    body = response.json()
    assert body["subdomain"] == "my-shop"
    assert body["id"] != str(foreign.id)


async def test_a_forged_host_does_not_turn_an_anonymous_visitor_into_the_owner(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    await seed_store(session, "cups")

    response = await api_client.get("/api/v1/stores/me", headers=host("cups"))

    assert response.status_code == 401
