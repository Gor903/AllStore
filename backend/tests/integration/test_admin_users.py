import uuid

import pytest
from httpx import AsyncClient, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog, User, UserRole
from tests.integration.conftest import (
    act_as,
    csrf_headers,
    register_buyer,
    register_seller,
    seed_staff,
    set_contacts,
)

pytestmark = pytest.mark.integration

ADMIN_USERS = "/api/v1/admin/users"
AUDIT_LOGS = "/api/v1/admin/audit-logs"
STORES_URL = "/api/v1/stores"


async def a_buyer(client: AsyncClient) -> str:
    client.cookies.clear()
    registered = await register_buyer(client, email=f"buyer-{uuid.uuid4().hex}@example.com")
    return str(registered.json()["id"])


async def a_shopkeeper(client: AsyncClient) -> str:
    client.cookies.clear()
    registered = await register_seller(client, email=f"seller-{uuid.uuid4().hex}@example.com")
    await client.post(
        STORES_URL, json={"subdomain": f"s{uuid.uuid4().hex[:8]}"}, headers=csrf_headers(client)
    )
    await set_contacts(client)
    return str(registered.json()["user"]["id"])


async def set_role(client: AsyncClient, user_id: str, role: str) -> Response:
    return await client.post(
        f"{ADMIN_USERS}/{user_id}/role", json={"role": role}, headers=csrf_headers(client)
    )


async def transfer_admin(client: AsyncClient, user_id: str) -> Response:
    return await client.post(
        f"{ADMIN_USERS}/{user_id}/transfer-admin", headers=csrf_headers(client)
    )


async def entries(session: AsyncSession) -> list[AuditLog]:
    result = await session.execute(select(AuditLog).order_by(AuditLog.created_at))
    return list(result.scalars().all())


async def test_an_admin_finds_an_account_by_part_of_its_email(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    await a_buyer(api_client)
    admin = await seed_staff(session, UserRole.ADMIN)
    await act_as(api_client, admin)

    found = await api_client.get(ADMIN_USERS, params={"q": "buyer-"})

    assert found.status_code == 200
    assert found.json()["total"] >= 1
    assert all("buyer-" in item["email"] for item in found.json()["items"])


async def test_a_search_that_matches_nothing_is_an_empty_page(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    admin = await seed_staff(session, UserRole.ADMIN)
    await act_as(api_client, admin)

    found = await api_client.get(ADMIN_USERS, params={"q": "нет-такого@example.com"})

    assert found.json() == {"items": [], "total": 0, "limit": 20, "offset": 0}


async def test_a_wildcard_in_the_search_does_not_widen_it(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    """Otherwise a single % would list every account on the platform."""
    await a_buyer(api_client)
    admin = await seed_staff(session, UserRole.ADMIN)
    await act_as(api_client, admin)

    assert (await api_client.get(ADMIN_USERS, params={"q": "%"})).json()["total"] == 0


async def test_an_admin_appoints_a_moderator(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    # until now this was a direct write to the database: power over other people's shops
    # handed out around the interface and without a trace
    buyer_id = await a_buyer(api_client)
    admin = await seed_staff(session, UserRole.ADMIN)
    await act_as(api_client, admin)

    response = await set_role(api_client, buyer_id, "moderator")

    assert response.status_code == 200
    assert response.json()["role"] == "moderator"


async def test_new_rights_apply_without_a_second_login(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    buyer_id = await a_buyer(api_client)
    buyer_cookies = dict(api_client.cookies)
    admin = await seed_staff(session, UserRole.ADMIN)
    await act_as(api_client, admin)
    await set_role(api_client, buyer_id, "moderator")

    api_client.cookies.clear()
    api_client.cookies.update(buyer_cookies)
    queue = await api_client.get("/api/v1/moderation/products")

    # the role is read from the database on every request, so the old session already has it
    assert queue.status_code == 200


async def test_the_administrator_role_is_never_taken_away_here(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    """There is one administrator and no screen that removes them: the role is handed over,
    not dropped, or the platform is left with nobody able to appoint anybody."""
    admin = await seed_staff(session, UserRole.ADMIN)
    await act_as(api_client, admin)

    response = await set_role(api_client, str(admin.id), "buyer")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "last_admin"
    assert (await api_client.get(f"{ADMIN_USERS}/{admin.id}")).json()["role"] == "admin"


async def test_nobody_is_promoted_to_administrator_by_a_role_change(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    """A second administrator is not a thing this platform has, so the screen that would
    create one refuses before the database has to."""
    buyer_id = await a_buyer(api_client)
    admin = await seed_staff(session, UserRole.ADMIN)
    await act_as(api_client, admin)

    response = await set_role(api_client, buyer_id, "admin")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "admin_account"
    assert (await api_client.get(f"{ADMIN_USERS}/{buyer_id}")).json()["role"] == "buyer"


async def test_an_administrator_hands_the_role_over(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    """One action, one transaction: the platform is never without an administrator, and
    never has two. The outgoing one stays staff — they were running the place a moment ago."""
    admin = await seed_staff(session, UserRole.ADMIN)
    successor = await seed_staff(session, UserRole.MODERATOR)
    await act_as(api_client, admin)

    response = await transfer_admin(api_client, str(successor.id))

    assert response.status_code == 200
    assert response.json()["role"] == "admin"
    assert (await api_client.get(f"{ADMIN_USERS}/{admin.id}")).status_code == 403
    await session.refresh(admin)
    await session.refresh(successor)
    assert admin.role is UserRole.MODERATOR
    assert successor.role is UserRole.ADMIN


async def test_the_handover_leaves_exactly_one_administrator(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    admin = await seed_staff(session, UserRole.ADMIN)
    successor = await seed_staff(session, UserRole.MODERATOR)
    await act_as(api_client, admin)

    await transfer_admin(api_client, str(successor.id))

    admins = await session.execute(select(User).where(User.role == UserRole.ADMIN))
    assert [user.id for user in admins.scalars().all()] == [successor.id]


async def test_the_handover_is_recorded(api_client: AsyncClient, session: AsyncSession) -> None:
    admin = await seed_staff(session, UserRole.ADMIN)
    successor = await seed_staff(session, UserRole.MODERATOR)
    await act_as(api_client, admin)

    await transfer_admin(api_client, str(successor.id))

    written = await entries(session)
    assert [entry.action for entry in written] == ["user.admin_transferred"]
    assert written[0].actor_user_id == admin.id
    assert written[0].entity_id == successor.id
    assert written[0].details == {"to": successor.email}


async def test_a_blocked_account_is_not_handed_the_platform(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    admin = await seed_staff(session, UserRole.ADMIN)
    successor = await seed_staff(session, UserRole.MODERATOR)
    await act_as(api_client, admin)
    await api_client.post(
        f"/api/v1/accounts/{successor.id}/block",
        json={"reason": "Нарушение регламента модерации"},
        headers=csrf_headers(api_client),
    )

    response = await transfer_admin(api_client, str(successor.id))

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "admin_account"


async def test_a_shopkeeper_is_not_handed_the_platform(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    """An administrator who owns a shop would be judging their own storefront."""
    seller_id = await a_shopkeeper(api_client)
    admin = await seed_staff(session, UserRole.ADMIN)
    await act_as(api_client, admin)

    response = await transfer_admin(api_client, seller_id)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "seller_account"


async def test_the_role_of_a_shopkeeper_is_not_changed_here(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    """Their storefront would be left running under an owner who is no longer a seller."""
    seller_id = await a_shopkeeper(api_client)
    admin = await seed_staff(session, UserRole.ADMIN)
    await act_as(api_client, admin)

    response = await set_role(api_client, seller_id, "buyer")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "seller_account"


async def test_a_missing_account_answers_404(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    admin = await seed_staff(session, UserRole.ADMIN)
    await act_as(api_client, admin)

    response = await set_role(api_client, str(uuid.uuid4()), "moderator")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "user_not_found"


@pytest.mark.parametrize("role", [UserRole.MODERATOR, UserRole.SELLER, UserRole.BUYER])
async def test_nobody_below_an_administrator_reaches_these_screens(
    api_client: AsyncClient, session: AsyncSession, role: UserRole
) -> None:
    buyer_id = await a_buyer(api_client)
    if role is UserRole.SELLER:
        await register_seller(api_client, email=f"seller-{uuid.uuid4().hex}@example.com")
    else:
        await act_as(api_client, await seed_staff(session, role))

    assert (await api_client.get(ADMIN_USERS)).status_code == 403
    assert (await set_role(api_client, buyer_id, "moderator")).status_code == 403
    assert (await transfer_admin(api_client, buyer_id)).status_code == 403
    assert (await api_client.get(AUDIT_LOGS)).status_code == 403


async def test_an_anonymous_visitor_reaches_nothing(api_client: AsyncClient) -> None:
    assert (await api_client.get(ADMIN_USERS)).status_code == 401
    assert (await api_client.get(AUDIT_LOGS)).status_code == 401


async def test_changing_a_role_without_the_csrf_header_is_forbidden(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    buyer_id = await a_buyer(api_client)
    admin = await seed_staff(session, UserRole.ADMIN)
    await act_as(api_client, admin)

    response = await api_client.post(f"{ADMIN_USERS}/{buyer_id}/role", json={"role": "moderator"})

    assert response.status_code == 403


async def test_a_role_change_leaves_a_record(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    buyer_id = await a_buyer(api_client)
    admin = await seed_staff(session, UserRole.ADMIN)
    await act_as(api_client, admin)

    await set_role(api_client, buyer_id, "moderator")

    written = await entries(session)
    assert [entry.action for entry in written] == ["user.role_changed"]
    assert written[0].actor_user_id == admin.id
    assert str(written[0].entity_id) == buyer_id
    assert written[0].details == {"from": "buyer", "to": "moderator"}


async def test_a_refused_action_leaves_no_record(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    """A journal that records attempts as if they happened is worse than none."""
    admin = await seed_staff(session, UserRole.ADMIN)
    await act_as(api_client, admin)

    await set_role(api_client, str(admin.id), "buyer")

    assert await entries(session) == []


async def test_setting_the_role_a_user_already_has_changes_nothing(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    buyer_id = await a_buyer(api_client)
    admin = await seed_staff(session, UserRole.ADMIN)
    await act_as(api_client, admin)

    response = await set_role(api_client, buyer_id, "buyer")

    assert response.status_code == 200
    # nothing happened, so nothing is written down
    assert await entries(session) == []


async def test_the_journal_names_who_acted_and_reads_newest_first(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    buyer_id = await a_buyer(api_client)
    admin = await seed_staff(session, UserRole.ADMIN)
    await act_as(api_client, admin)
    await set_role(api_client, buyer_id, "moderator")
    await set_role(api_client, buyer_id, "buyer")

    body = (await api_client.get(AUDIT_LOGS)).json()

    assert body["total"] == 2
    assert [item["action"] for item in body["items"]] == ["user.role_changed", "user.role_changed"]
    assert body["items"][0]["actor_email"] == admin.email
    assert body["items"][0]["details"] == {"from": "moderator", "to": "buyer"}


async def test_an_administrator_does_not_hand_the_platform_to_themselves(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    admin = await seed_staff(session, UserRole.ADMIN)
    await act_as(api_client, admin)

    response = await transfer_admin(api_client, str(admin.id))

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "admin_account"
