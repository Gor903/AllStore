"""Global bans: who may hand one out, what it takes away, and what it leaves behind.

The last of those is the point. A ban here is a status and a row, never a deletion: the shop,
the products, the complaints and every verdict ever passed stay where they were, and lifting
the ban does not erase that it happened.
"""

import uuid

import pytest
from httpx import AsyncClient, Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AccountBlock, Business, Product, User, UserRole, UserStatus
from tests.integration.conftest import (
    a_live_shop,
    a_published_product,
    act_as,
    anonymous,
    csrf_headers,
    login,
    register_buyer,
    seed_staff,
    switch,
)

pytestmark = pytest.mark.integration

ACCOUNTS = "/api/v1/accounts"
CATALOG_PRODUCTS = "/api/v1/catalog/products"
CATALOG_STORES = "/api/v1/catalog/stores"
STOREFRONT = "/api/v1/storefront"
REASON = "Оскорбления в переписке с продавцом"


async def block(client: AsyncClient, user_id: str, reason: str = REASON) -> Response:
    return await client.post(
        f"{ACCOUNTS}/{user_id}/block", json={"reason": reason}, headers=csrf_headers(client)
    )


async def unblock(client: AsyncClient, user_id: str, **body: str) -> Response:
    return await client.post(
        f"{ACCOUNTS}/{user_id}/unblock", json=body, headers=csrf_headers(client)
    )


async def a_buyer(client: AsyncClient) -> str:
    client.cookies.clear()
    registered = await register_buyer(client, email=f"buyer-{uuid.uuid4().hex}@example.com")
    return str(registered.json()["id"])


async def blocks_of(session: AsyncSession, user_id: str) -> list[AccountBlock]:
    result = await session.execute(
        select(AccountBlock)
        .where(AccountBlock.user_id == uuid.UUID(user_id))
        .order_by(AccountBlock.created_at)
    )
    return list(result.scalars().all())


async def test_a_moderator_bars_a_buyer(api_client: AsyncClient, session: AsyncSession) -> None:
    buyer_id = await a_buyer(api_client)
    moderator = await seed_staff(session, UserRole.MODERATOR)
    await act_as(api_client, moderator)

    response = await block(api_client, buyer_id)

    assert response.status_code == 200
    assert response.json()["status"] == "blocked"


async def test_a_moderator_bars_a_seller(api_client: AsyncClient, session: AsyncSession) -> None:
    """Until this stage the only account a moderator could touch was a shop, through business
    moderation; the person behind it stayed active and signed in as if nothing had happened."""
    shop = await a_live_shop(api_client, session, "barred")
    switch(api_client, shop.moderator)

    response = await block(api_client, shop.seller_id)

    assert response.status_code == 200
    assert response.json()["status"] == "blocked"


@pytest.mark.parametrize("role", [UserRole.MODERATOR, UserRole.ADMIN])
async def test_a_moderator_bars_nobody_at_their_own_level_or_above(
    api_client: AsyncClient, session: AsyncSession, role: UserRole
) -> None:
    target = await seed_staff(session, role)
    moderator = await seed_staff(session, UserRole.MODERATOR)
    await act_as(api_client, moderator)

    response = await block(api_client, str(target.id))

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "not_allowed"


async def test_an_administrator_bars_a_moderator(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    moderator = await seed_staff(session, UserRole.MODERATOR)
    admin = await seed_staff(session, UserRole.ADMIN)
    await act_as(api_client, admin)

    response = await block(api_client, str(moderator.id))

    assert response.status_code == 200
    assert response.json()["status"] == "blocked"


async def test_an_administrator_cannot_bar_themselves(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    """The one account that can appoint anybody is the one account that must not be able to
    lock itself out by a slip of the mouse."""
    admin = await seed_staff(session, UserRole.ADMIN)
    await act_as(api_client, admin)

    response = await block(api_client, str(admin.id))

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "not_allowed"
    assert "Себя" in response.json()["error"]["message"]


async def test_a_moderator_cannot_bar_themselves(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    moderator = await seed_staff(session, UserRole.MODERATOR)
    await act_as(api_client, moderator)

    assert (await block(api_client, str(moderator.id))).status_code == 403


@pytest.mark.parametrize("role", [UserRole.BUYER, UserRole.SELLER])
async def test_nobody_outside_the_staff_reaches_these_routes(
    api_client: AsyncClient, session: AsyncSession, role: UserRole
) -> None:
    target_id = await a_buyer(api_client)
    actor = await seed_staff(session, role)
    await act_as(api_client, actor)

    assert (await block(api_client, target_id)).status_code == 403
    assert (await unblock(api_client, target_id)).status_code == 403
    assert (await api_client.get(f"{ACCOUNTS}/{target_id}/blocks")).status_code == 403


async def test_an_anonymous_visitor_reaches_nothing(api_client: AsyncClient) -> None:
    await anonymous(api_client)
    target = uuid.uuid4()

    assert (await api_client.get(f"{ACCOUNTS}/{target}/blocks")).status_code == 401


async def test_barring_without_a_reason_is_refused(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    """A ban the person cannot answer is a ban they cannot appeal."""
    buyer_id = await a_buyer(api_client)
    moderator = await seed_staff(session, UserRole.MODERATOR)
    await act_as(api_client, moderator)

    assert (await block(api_client, buyer_id, reason="   ")).status_code == 422
    assert (await block(api_client, buyer_id, reason="")).status_code == 422


async def test_barring_without_the_csrf_header_is_forbidden(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    buyer_id = await a_buyer(api_client)
    moderator = await seed_staff(session, UserRole.MODERATOR)
    await act_as(api_client, moderator)

    response = await api_client.post(f"{ACCOUNTS}/{buyer_id}/block", json={"reason": REASON})

    assert response.status_code == 403


async def test_the_session_ends_at_once(api_client: AsyncClient, session: AsyncSession) -> None:
    buyer_id = await a_buyer(api_client)
    buyer_cookies = dict(api_client.cookies)
    moderator = await seed_staff(session, UserRole.MODERATOR)
    await act_as(api_client, moderator)
    await block(api_client, buyer_id)

    switch(api_client, buyer_cookies)
    response = await api_client.get("/api/v1/users/me")

    # the status is re-read on every request, so the session dies without waiting for the
    # access token to expire; 403 rather than 401 — the token is valid, the account is not
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "account_not_active"


async def test_the_session_cannot_renew_itself(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    """The access token is short-lived, so a ban that left the refresh token alone would be
    a ban the browser quietly renews its way out of."""
    buyer_id = await a_buyer(api_client)
    buyer_cookies = dict(api_client.cookies)
    moderator = await seed_staff(session, UserRole.MODERATOR)
    await act_as(api_client, moderator)
    await block(api_client, buyer_id)

    switch(api_client, buyer_cookies)
    response = await api_client.post("/api/v1/auth/refresh", headers=csrf_headers(api_client))

    assert response.status_code in (401, 403)


async def test_a_barred_account_cannot_log_back_in(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    buyer_id = await a_buyer(api_client)
    buyer = await session.get(User, uuid.UUID(buyer_id))
    assert buyer is not None
    moderator = await seed_staff(session, UserRole.MODERATOR)
    await act_as(api_client, moderator)
    await block(api_client, buyer_id)

    api_client.cookies.clear()
    response = await login(api_client, buyer.email, "buyer-password-1")

    assert response.status_code in (401, 403)
    assert buyer.status is UserStatus.BLOCKED


async def test_barring_a_seller_takes_their_shelf_down(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    """No second write and no window: the public filter reads the owner's status, so the
    storefront goes dark in the same statement the account does."""
    shop = await a_live_shop(api_client, session, "darkened")
    await a_published_product(api_client, session, shop, name="Кружка керамическая")
    switch(api_client, shop.moderator)
    await block(api_client, shop.seller_id)
    await anonymous(api_client)

    assert (await api_client.get(CATALOG_PRODUCTS)).json()["total"] == 0
    assert (await api_client.get(CATALOG_STORES)).json()["total"] == 0
    assert (await api_client.get(f"{STOREFRONT}/{shop.subdomain}")).status_code == 404


async def test_a_barred_sellers_product_is_gone_from_a_direct_link(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    shop = await a_live_shop(api_client, session, "directlink")
    product_id = await a_published_product(api_client, session, shop)
    switch(api_client, shop.moderator)
    await block(api_client, shop.seller_id)
    await anonymous(api_client)

    response = await api_client.get(f"{CATALOG_PRODUCTS}/{product_id}")

    assert response.status_code == 404


async def test_barring_a_seller_deletes_nothing(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    shop = await a_live_shop(api_client, session, "intact")
    product_id = await a_published_product(api_client, session, shop)
    switch(api_client, shop.moderator)

    await block(api_client, shop.seller_id)

    assert await session.get(User, uuid.UUID(shop.seller_id)) is not None
    assert await session.get(Business, uuid.UUID(shop.business_id)) is not None
    assert await session.get(Product, uuid.UUID(product_id)) is not None


async def test_lifting_the_ban_puts_the_shop_back(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    shop = await a_live_shop(api_client, session, "restored")
    await a_published_product(api_client, session, shop, name="Кружка керамическая")
    switch(api_client, shop.moderator)
    await block(api_client, shop.seller_id)

    await unblock(api_client, shop.seller_id)
    await anonymous(api_client)

    assert (await api_client.get(CATALOG_PRODUCTS)).json()["total"] == 1
    assert (await api_client.get(f"{STOREFRONT}/{shop.subdomain}")).status_code == 200


async def test_the_same_account_is_not_barred_twice_over(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    """One ban in force at a time, so lifting it is one action rather than a guess at how
    many are stacked up."""
    buyer_id = await a_buyer(api_client)
    moderator = await seed_staff(session, UserRole.MODERATOR)
    await act_as(api_client, moderator)
    await block(api_client, buyer_id)

    response = await block(api_client, buyer_id)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "already_blocked"
    assert len(await blocks_of(session, buyer_id)) == 1


async def test_lifting_a_ban_that_is_not_there_is_refused(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    buyer_id = await a_buyer(api_client)
    moderator = await seed_staff(session, UserRole.MODERATOR)
    await act_as(api_client, moderator)

    response = await unblock(api_client, buyer_id)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "not_blocked"


async def test_lifting_a_ban_keeps_it_in_the_history(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    buyer_id = await a_buyer(api_client)
    moderator = await seed_staff(session, UserRole.MODERATOR)
    await act_as(api_client, moderator)
    await block(api_client, buyer_id)

    await unblock(api_client, buyer_id, reason="Разобрались, недоразумение")

    history = await blocks_of(session, buyer_id)
    assert len(history) == 1
    assert history[0].reason == REASON
    assert history[0].revoked_at is not None
    assert history[0].revoked_by_user_id == moderator.id
    assert history[0].revoke_reason == "Разобрались, недоразумение"


async def test_a_second_ban_is_a_second_row(api_client: AsyncClient, session: AsyncSession) -> None:
    """Whether this has happened before is a question the next moderator has to be able to ask."""
    buyer_id = await a_buyer(api_client)
    moderator = await seed_staff(session, UserRole.MODERATOR)
    await act_as(api_client, moderator)
    await block(api_client, buyer_id, reason="Первый раз")
    await unblock(api_client, buyer_id)

    await block(api_client, buyer_id, reason="Второй раз")

    history = await blocks_of(session, buyer_id)
    assert [item.reason for item in history] == ["Первый раз", "Второй раз"]
    assert [item.in_force for item in history] == [False, True]


async def test_the_history_reads_newest_first_and_names_who_decided(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    buyer_id = await a_buyer(api_client)
    moderator = await seed_staff(session, UserRole.MODERATOR)
    await act_as(api_client, moderator)
    await block(api_client, buyer_id, reason="Первый раз")
    await unblock(api_client, buyer_id)
    await block(api_client, buyer_id, reason="Второй раз")

    body = (await api_client.get(f"{ACCOUNTS}/{buyer_id}/blocks")).json()

    assert body["total"] == 2
    assert [item["reason"] for item in body["items"]] == ["Второй раз", "Первый раз"]
    assert body["items"][0]["actor_email"] == moderator.email
    assert body["items"][0]["in_force"] is True
    assert body["items"][1]["revoked_by_email"] == moderator.email


async def test_an_administrator_lifts_a_ban_a_moderator_handed_out(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    buyer_id = await a_buyer(api_client)
    moderator = await seed_staff(session, UserRole.MODERATOR)
    admin = await seed_staff(session, UserRole.ADMIN)
    await act_as(api_client, moderator)
    await block(api_client, buyer_id)

    await act_as(api_client, admin)
    response = await unblock(api_client, buyer_id)

    assert response.status_code == 200
    assert response.json()["status"] == "active"
    history = await blocks_of(session, buyer_id)
    assert history[0].actor_user_id == moderator.id
    assert history[0].revoked_by_user_id == admin.id


async def test_a_moderator_does_not_lift_a_ban_on_a_moderator(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    barred = await seed_staff(session, UserRole.MODERATOR)
    admin = await seed_staff(session, UserRole.ADMIN)
    await act_as(api_client, admin)
    await block(api_client, str(barred.id))

    moderator = await seed_staff(session, UserRole.MODERATOR)
    await act_as(api_client, moderator)
    response = await unblock(api_client, str(barred.id))

    assert response.status_code == 403


async def test_the_history_of_an_unknown_account_answers_404(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    moderator = await seed_staff(session, UserRole.MODERATOR)
    await act_as(api_client, moderator)

    response = await api_client.get(f"{ACCOUNTS}/{uuid.uuid4()}/blocks")

    assert response.status_code == 404


async def test_every_decision_is_journalled(api_client: AsyncClient, session: AsyncSession) -> None:
    buyer_id = await a_buyer(api_client)
    moderator = await seed_staff(session, UserRole.MODERATOR)
    await act_as(api_client, moderator)

    await block(api_client, buyer_id)
    await unblock(api_client, buyer_id)

    from app.models import AuditLog

    written = (
        (await session.execute(select(AuditLog).order_by(AuditLog.created_at))).scalars().all()
    )
    assert [entry.action for entry in written] == ["user.blocked", "user.unblocked"]
    assert all(entry.actor_user_id == moderator.id for entry in written)
    assert written[0].details == {"reason": REASON}


async def test_a_refused_ban_writes_nothing_down(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    admin = await seed_staff(session, UserRole.ADMIN)
    await act_as(api_client, admin)

    await block(api_client, str(admin.id))

    written = await session.execute(select(func.count()).select_from(AccountBlock))
    assert written.scalar_one() == 0
