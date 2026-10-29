import uuid
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models import Business, BusinessStatus, Store, User, UserRole
from app.repositories import stores as stores_repo
from app.services import stores as stores_service
from tests.integration.conftest import csrf_headers, register_buyer, register_seller

pytestmark = pytest.mark.integration

CREATE_URL = "/api/v1/stores"
ME_URL = "/api/v1/stores/me"


async def create_store(client: AsyncClient, subdomain: str) -> Any:
    return await client.post(
        CREATE_URL, json={"subdomain": subdomain}, headers=csrf_headers(client)
    )


async def seed_business_with_store(session: AsyncSession, subdomain: str) -> Business:
    """Straight into the database — the service path is what the test under it exercises."""
    user = User(
        email=f"seller-{uuid.uuid4().hex}@example.com",
        password_hash="$argon2id$fake",
        role=UserRole.SELLER,
    )
    session.add(user)
    await session.flush()
    business = Business(owner_user_id=user.id, legal_name='ИП "Тест"', display_name="Тест")
    session.add(business)
    await session.flush()
    session.add(Store(business_id=business.id, subdomain=subdomain))
    await session.flush()
    return business


async def register_second_seller(client: AsyncClient, session: AsyncSession) -> None:
    """A seller registration replaces the cookies, so the client acts as the new account."""
    client.cookies.clear()
    await register_seller(client, session, email=f"seller-{uuid.uuid4().hex}@example.com")


async def test_seller_creates_a_store(api_client: AsyncClient, session: AsyncSession) -> None:
    await register_seller(api_client, session)

    response = await create_store(api_client, "cups")

    assert response.status_code == 201
    body = response.json()
    assert body["subdomain"] == "cups"
    assert body["status"] == "draft"
    assert body["theme_id"] == "default"


async def test_subdomain_is_stored_in_lower_case(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    """DNS reads a label case-insensitively, so CUPS is the same address, not a broken one."""
    await register_seller(api_client, session)

    response = await create_store(api_client, "  CUPS  ")

    assert response.status_code == 201
    assert response.json()["subdomain"] == "cups"


async def test_taken_subdomain_is_rejected_with_409(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    await register_seller(api_client, session)
    assert (await create_store(api_client, "cups")).status_code == 201
    await register_second_seller(api_client, session)

    response = await create_store(api_client, "cups")

    assert response.status_code == 409
    error = response.json()["error"]
    assert error["code"] == "subdomain_taken"
    assert error["message"] == "Этот адрес уже занят, выберите другой"
    assert error["details"][0]["loc"] == ["body", "subdomain"]


@pytest.mark.parametrize("subdomain", ["www", "api", "admin", "dashboard", "WWW"])
async def test_reserved_subdomain_is_rejected(
    api_client: AsyncClient, session: AsyncSession, subdomain: str
) -> None:
    await register_seller(api_client, session)

    response = await create_store(api_client, subdomain)

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "subdomain_reserved"
    assert error["details"][0]["loc"] == ["body", "subdomain"]


@pytest.mark.parametrize(
    "subdomain",
    [
        "ab",  # shorter than three characters
        "-cups",  # leading hyphen
        "cups-",  # trailing hyphen
        "my_cups",  # underscore is not a DNS label character
        "my.cups",  # a dot would add another level
        "c" * 64,  # longer than a DNS label
        "",  # empty
    ],
)
async def test_malformed_subdomain_is_rejected(
    api_client: AsyncClient, session: AsyncSession, subdomain: str
) -> None:
    await register_seller(api_client, session)

    response = await create_store(api_client, subdomain)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_failed"


async def test_second_store_for_the_same_business_is_rejected(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    await register_seller(api_client, session)
    assert (await create_store(api_client, "cups")).status_code == 201

    response = await create_store(api_client, "mugs")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "store_already_exists"


async def test_blocked_business_cannot_create_a_store(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    await register_seller(api_client, session)
    business = (await session.execute(select(Business))).scalars().one()
    business.status = BusinessStatus.BLOCKED
    await session.flush()

    response = await create_store(api_client, "cups")

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "business_not_eligible"


async def test_seller_without_a_business_gets_404(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    await register_seller(api_client, session)
    await session.execute(delete(Business))
    await session.flush()

    assert (await create_store(api_client, "cups")).status_code == 404
    assert (await api_client.get(ME_URL)).status_code == 404


async def test_buyer_cannot_create_a_store(api_client: AsyncClient) -> None:
    await register_buyer(api_client)

    response = await create_store(api_client, "cups")

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "permission_denied"


async def test_anonymous_cannot_create_a_store(api_client: AsyncClient) -> None:
    """403, not 401: the CSRF gate answers before authentication, as on /auth/refresh."""
    response = await api_client.post(CREATE_URL, json={"subdomain": "cups"})

    assert response.status_code == 403
    assert (await api_client.get(ME_URL)).status_code == 401


async def test_creating_a_store_without_the_csrf_header_is_forbidden(
    api_client: AsyncClient,
    session: AsyncSession,
) -> None:
    await register_seller(api_client, session)

    response = await api_client.post(CREATE_URL, json={"subdomain": "cups"})

    assert response.status_code == 403


async def test_store_of_the_seller_is_readable_after_creation(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    await register_seller(api_client, session)
    assert (await api_client.get(ME_URL)).status_code == 404
    created = await create_store(api_client, "cups")

    response = await api_client.get(ME_URL)

    assert response.status_code == 200
    assert response.json()["id"] == created.json()["id"]


async def test_another_seller_does_not_see_a_foreign_store(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    await register_seller(api_client, session)
    assert (await create_store(api_client, "cups")).status_code == 201
    await register_second_seller(api_client, session)

    response = await api_client.get(ME_URL)

    assert response.status_code == 404


async def test_an_unrelated_integrity_error_is_not_reported_as_taken(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Only the subdomain race becomes a 409 — any other violation stays an error, not a lie."""
    business = await seed_business_with_store(session, subdomain="cups")

    async def nothing_found(*_: object, **__: object) -> Store | None:
        return None

    # both pre-checks pass, so the insert trips ix_stores_business_id instead
    monkeypatch.setattr(stores_repo, "get_by_business", nothing_found)
    monkeypatch.setattr(stores_repo, "get_by_subdomain", nothing_found)

    with pytest.raises(IntegrityError):
        await stores_service.create_store(session, get_settings(), business, "mugs")


async def test_losing_the_race_on_the_unique_index_is_reported_as_taken(
    api_client: AsyncClient, session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Simulates the window between the availability check and the insert of a second seller."""
    await register_seller(api_client, session)
    assert (await create_store(api_client, "cups")).status_code == 201
    await register_second_seller(api_client, session)

    async def taken_by_nobody(*_: object, **__: object) -> Store | None:
        return None

    monkeypatch.setattr(stores_repo, "get_by_subdomain", taken_by_nobody)
    response = await create_store(api_client, "cups")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "subdomain_taken"
