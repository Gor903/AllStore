import uuid

import pytest
from httpx import AsyncClient, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models import AuditLog, User, UserRole, UserStatus
from tests.integration.conftest import (
    csrf_headers,
    login,
    register_buyer,
    register_seller,
    set_contacts,
)

pytestmark = pytest.mark.integration

ADMIN_USERS = "/api/v1/admin/users"
AUDIT_LOGS = "/api/v1/admin/audit-logs"
STORES_URL = "/api/v1/stores"
PASSWORD = "staff-password-1"
REASON = "Оскорбления в переписке с продавцом"


async def seed_staff(session: AsyncSession, role: UserRole) -> User:
    """Moderators and administrators have no self-registration, so they are seeded."""
    user = User(
        email=f"{role}-{uuid.uuid4().hex}@example.com",
        password_hash=hash_password(PASSWORD),
        role=role,
    )
    session.add(user)
    await session.flush()
    return user


async def act_as(client: AsyncClient, user: User) -> None:
    client.cookies.clear()
    assert (await login(client, user.email, PASSWORD)).status_code == 200


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


async def test_the_last_administrator_keeps_their_role(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    admin = await seed_staff(session, UserRole.ADMIN)
    await act_as(api_client, admin)

    response = await set_role(api_client, str(admin.id), "buyer")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "last_admin"
    assert (await api_client.get(f"{ADMIN_USERS}/{admin.id}")).json()["role"] == "admin"


async def test_an_administrator_steps_down_once_another_exists(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    admin = await seed_staff(session, UserRole.ADMIN)
    await seed_staff(session, UserRole.ADMIN)
    await act_as(api_client, admin)

    response = await set_role(api_client, str(admin.id), "buyer")

    assert response.status_code == 200
    assert response.json()["role"] == "buyer"


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


async def test_an_admin_blocks_and_unblocks_a_buyer(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    buyer_id = await a_buyer(api_client)
    admin = await seed_staff(session, UserRole.ADMIN)
    await act_as(api_client, admin)

    blocked = await api_client.post(
        f"{ADMIN_USERS}/{buyer_id}/block", json={"reason": REASON}, headers=csrf_headers(api_client)
    )
    restored = await api_client.post(
        f"{ADMIN_USERS}/{buyer_id}/unblock", headers=csrf_headers(api_client)
    )

    assert blocked.json()["status"] == "blocked"
    assert restored.json()["status"] == "active"


async def test_blocking_takes_the_session_away_at_once(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    buyer_id = await a_buyer(api_client)
    buyer_cookies = dict(api_client.cookies)
    admin = await seed_staff(session, UserRole.ADMIN)
    await act_as(api_client, admin)
    await api_client.post(
        f"{ADMIN_USERS}/{buyer_id}/block", json={"reason": REASON}, headers=csrf_headers(api_client)
    )

    api_client.cookies.clear()
    api_client.cookies.update(buyer_cookies)

    # the status is re-read on every request, so the session dies without waiting for the
    # access token to expire; 403 rather than 401 — the token is valid, the account is not
    response = await api_client.get("/api/v1/users/me")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "account_not_active"


async def test_blocking_without_a_reason_is_refused(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    buyer_id = await a_buyer(api_client)
    admin = await seed_staff(session, UserRole.ADMIN)
    await act_as(api_client, admin)

    response = await api_client.post(
        f"{ADMIN_USERS}/{buyer_id}/block", json={"reason": "   "}, headers=csrf_headers(api_client)
    )

    assert response.status_code == 422


async def test_an_administrator_is_not_blocked_here(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    admin = await seed_staff(session, UserRole.ADMIN)
    other = await seed_staff(session, UserRole.ADMIN)
    await act_as(api_client, admin)

    response = await api_client.post(
        f"{ADMIN_USERS}/{other.id}/block",
        json={"reason": REASON},
        headers=csrf_headers(api_client),
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "admin_account"


async def test_a_shopkeeper_is_barred_through_business_moderation(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    """Blocking the account here would lock the owner out while the shop kept selling."""
    seller_id = await a_shopkeeper(api_client)
    admin = await seed_staff(session, UserRole.ADMIN)
    await act_as(api_client, admin)

    response = await api_client.post(
        f"{ADMIN_USERS}/{seller_id}/block",
        json={"reason": REASON},
        headers=csrf_headers(api_client),
    )

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


async def test_every_action_leaves_a_record(api_client: AsyncClient, session: AsyncSession) -> None:
    buyer_id = await a_buyer(api_client)
    admin = await seed_staff(session, UserRole.ADMIN)
    await act_as(api_client, admin)

    await set_role(api_client, buyer_id, "moderator")
    await api_client.post(
        f"{ADMIN_USERS}/{buyer_id}/block", json={"reason": REASON}, headers=csrf_headers(api_client)
    )
    await api_client.post(f"{ADMIN_USERS}/{buyer_id}/unblock", headers=csrf_headers(api_client))

    written = await entries(session)
    assert [entry.action for entry in written] == [
        "user.role_changed",
        "user.blocked",
        "user.unblocked",
    ]
    assert all(entry.actor_user_id == admin.id for entry in written)
    assert all(str(entry.entity_id) == buyer_id for entry in written)
    assert written[0].details == {"from": "buyer", "to": "moderator"}
    assert written[1].details == {"reason": REASON}


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
    await api_client.post(
        f"{ADMIN_USERS}/{buyer_id}/block", json={"reason": REASON}, headers=csrf_headers(api_client)
    )

    body = (await api_client.get(AUDIT_LOGS)).json()

    assert body["total"] == 2
    assert [item["action"] for item in body["items"]] == ["user.blocked", "user.role_changed"]
    assert body["items"][0]["actor_email"] == admin.email
    assert body["items"][0]["details"] == {"reason": REASON}


async def test_a_blocked_account_cannot_log_back_in(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    buyer_id = await a_buyer(api_client)
    buyer = await session.get(User, uuid.UUID(buyer_id))
    assert buyer is not None
    admin = await seed_staff(session, UserRole.ADMIN)
    await act_as(api_client, admin)
    await api_client.post(
        f"{ADMIN_USERS}/{buyer_id}/block", json={"reason": REASON}, headers=csrf_headers(api_client)
    )

    api_client.cookies.clear()
    response = await login(api_client, buyer.email, "buyer-password-1")

    assert response.status_code in (401, 403)
    assert buyer.status is UserStatus.BLOCKED
