"""A seller closing their own door, and the line that keeps it their own.

The point of this stage is the difference between two things that sound alike: barring
somebody from one shop, and barring them from the platform. The first is a seller's to
decide and reaches exactly one storefront; the second is a moderator's. Most of what is
asserted here is that the first never turns into the second.
"""

import uuid

import pytest
from httpx import AsyncClient, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog, BusinessCustomerBlock, User, UserRole, UserStatus
from tests.integration.conftest import (
    a_live_shop,
    a_published_product,
    act_as,
    anonymous,
    csrf_headers,
    register_buyer,
    seed_staff,
    switch,
)

pytestmark = pytest.mark.integration

BLOCKED_BUYERS = "/api/v1/stores/me/blocked-buyers"
STORE_BLOCKS = "/api/v1/store-blocks"
ACCOUNTS = "/api/v1/accounts"
CATALOG_PRODUCTS = "/api/v1/catalog/products"
CATALOG_STORES = "/api/v1/catalog/stores"
STOREFRONT = "/api/v1/storefront"
REPORTS = "/api/v1/reports"
REASON = "Хамство в переписке и срыв трёх сделок подряд"


async def a_buyer(client: AsyncClient) -> tuple[str, str, dict[str, str]]:
    """Returns the buyer's id, address and cookies."""
    client.cookies.clear()
    email = f"buyer-{uuid.uuid4().hex}@example.com"
    registered = await register_buyer(client, email=email)
    assert registered.status_code == 201
    return str(registered.json()["id"]), email, dict(client.cookies)


async def shut_out(client: AsyncClient, email: str, reason: str = REASON) -> Response:
    return await client.post(
        BLOCKED_BUYERS, json={"email": email, "reason": reason}, headers=csrf_headers(client)
    )


async def test_a_seller_closes_the_shop_to_one_buyer(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    shop = await a_live_shop(api_client, session, "closeddoor")
    _, email, _ = await a_buyer(api_client)
    switch(api_client, shop.seller)

    response = await shut_out(api_client, email)

    assert response.status_code == 201
    assert response.json()["buyer_email"] == email
    assert response.json()["in_force"] is True


async def test_the_buyer_stays_active_everywhere_else(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    """The whole point of the stage: a shop's door is not the platform's."""
    shop = await a_live_shop(api_client, session, "notglobal")
    buyer_id, email, buyer = await a_buyer(api_client)
    switch(api_client, shop.seller)
    await shut_out(api_client, email)

    switch(api_client, buyer)
    assert (await api_client.get("/api/v1/users/me")).status_code == 200
    stored = await session.get(User, uuid.UUID(buyer_id))
    assert stored is not None
    assert stored.status is UserStatus.ACTIVE


async def test_the_shop_disappears_from_the_catalogue_for_that_buyer(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    shop = await a_live_shop(api_client, session, "gonefromlist")
    await a_published_product(api_client, session, shop, name="Кружка керамическая")
    _, email, buyer = await a_buyer(api_client)
    switch(api_client, shop.seller)
    await shut_out(api_client, email)

    switch(api_client, buyer)
    assert (await api_client.get(CATALOG_PRODUCTS)).json()["total"] == 0
    assert (await api_client.get(CATALOG_STORES)).json()["total"] == 0


async def test_everybody_else_still_sees_the_shop(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    shop = await a_live_shop(api_client, session, "stillthere")
    await a_published_product(api_client, session, shop, name="Кружка керамическая")
    _, email, _ = await a_buyer(api_client)
    switch(api_client, shop.seller)
    await shut_out(api_client, email)

    await anonymous(api_client)
    assert (await api_client.get(CATALOG_PRODUCTS)).json()["total"] == 1
    _, _, other = await a_buyer(api_client)
    switch(api_client, other)
    assert (await api_client.get(CATALOG_PRODUCTS)).json()["total"] == 1


async def test_a_saved_link_to_the_product_stops_working(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    """The frontend hiding a card is not a protection; the filter is."""
    shop = await a_live_shop(api_client, session, "savedlink")
    product_id = await a_published_product(api_client, session, shop)
    _, email, buyer = await a_buyer(api_client)
    switch(api_client, shop.seller)
    await shut_out(api_client, email)

    switch(api_client, buyer)
    response = await api_client.get(f"{CATALOG_PRODUCTS}/{product_id}")

    assert response.status_code == 404


async def test_the_storefront_says_so_rather_than_pretending_to_be_missing(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    """They were shopping there a week ago, so a 404 would be a riddle, not a protection."""
    shop = await a_live_shop(api_client, session, "straightanswer")
    _, email, buyer = await a_buyer(api_client)
    switch(api_client, shop.seller)
    await shut_out(api_client, email)

    switch(api_client, buyer)
    response = await api_client.get(f"{STOREFRONT}/{shop.subdomain}")

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "store_access_blocked"


async def test_a_barred_buyer_can_still_complain_about_the_shop(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    """A complaint is addressed to moderators, not to the shop. Closing your door to somebody
    must not close the one way they have of being heard about it."""
    shop = await a_live_shop(api_client, session, "stillcomplains")
    _, email, buyer = await a_buyer(api_client)
    switch(api_client, shop.seller)
    await shut_out(api_client, email)

    switch(api_client, buyer)
    response = await api_client.post(
        REPORTS, json={"subdomain": shop.subdomain, "reason": "Закрыли доступ после предоплаты"}
    )

    assert response.status_code == 201


async def test_a_seller_cannot_touch_another_shops_door(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    first = await a_live_shop(api_client, session, "mineonly")
    _, email, _ = await a_buyer(api_client)
    switch(api_client, first.seller)
    created = await shut_out(api_client, email)
    block_id = created.json()["id"]

    second = await a_live_shop(api_client, session, "someoneelse")
    switch(api_client, second.seller)
    response = await api_client.post(
        f"{BLOCKED_BUYERS}/{block_id}/revoke", headers=csrf_headers(api_client)
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "not_your_block"


async def test_a_seller_sees_only_their_own_door(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    first = await a_live_shop(api_client, session, "listmine")
    _, email, _ = await a_buyer(api_client)
    switch(api_client, first.seller)
    await shut_out(api_client, email)

    second = await a_live_shop(api_client, session, "listtheirs")
    switch(api_client, second.seller)
    body = (await api_client.get(BLOCKED_BUYERS)).json()

    assert body["total"] == 0


async def test_a_seller_cannot_shut_out_a_moderator(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    """Only buyers walk into a shop. Anything else would be a seller reaching for the staff."""
    shop = await a_live_shop(api_client, session, "notstaff")
    moderator = await seed_staff(session, UserRole.MODERATOR)
    switch(api_client, shop.seller)

    response = await shut_out(api_client, moderator.email)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "not_a_buyer"


async def test_shutting_somebody_out_twice_is_refused(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    shop = await a_live_shop(api_client, session, "onceonly")
    _, email, _ = await a_buyer(api_client)
    switch(api_client, shop.seller)
    await shut_out(api_client, email)

    response = await shut_out(api_client, email)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "already_blocked"


async def test_a_door_closed_on_nobody_answers_404(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    shop = await a_live_shop(api_client, session, "nosuchbuyer")
    switch(api_client, shop.seller)

    response = await shut_out(api_client, f"nobody-{uuid.uuid4().hex}@example.com")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "buyer_not_found"


async def test_a_reason_is_required(api_client: AsyncClient, session: AsyncSession) -> None:
    shop = await a_live_shop(api_client, session, "needsreason")
    _, email, _ = await a_buyer(api_client)
    switch(api_client, shop.seller)

    assert (await shut_out(api_client, email, reason="   ")).status_code == 422


async def test_closing_the_door_without_the_csrf_header_is_forbidden(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    shop = await a_live_shop(api_client, session, "needscsrf")
    _, email, _ = await a_buyer(api_client)
    switch(api_client, shop.seller)

    response = await api_client.post(BLOCKED_BUYERS, json={"email": email, "reason": REASON})

    assert response.status_code == 403


@pytest.mark.parametrize("role", [UserRole.BUYER, UserRole.MODERATOR, UserRole.ADMIN])
async def test_nobody_but_a_seller_manages_a_shops_door(
    api_client: AsyncClient, session: AsyncSession, role: UserRole
) -> None:
    actor = await seed_staff(session, role)
    await act_as(api_client, actor)

    assert (await api_client.get(BLOCKED_BUYERS)).status_code == 403
    assert (await shut_out(api_client, "someone@example.com")).status_code == 403


async def test_lifting_it_lets_the_buyer_back_in(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    shop = await a_live_shop(api_client, session, "welcomeback")
    await a_published_product(api_client, session, shop, name="Кружка керамическая")
    _, email, buyer = await a_buyer(api_client)
    switch(api_client, shop.seller)
    created = await shut_out(api_client, email)

    lifted = await api_client.post(
        f"{BLOCKED_BUYERS}/{created.json()['id']}/revoke", headers=csrf_headers(api_client)
    )

    assert lifted.status_code == 200
    assert lifted.json()["in_force"] is False
    switch(api_client, buyer)
    assert (await api_client.get(CATALOG_PRODUCTS)).json()["total"] == 1
    assert (await api_client.get(f"{STOREFRONT}/{shop.subdomain}")).status_code == 200


async def test_lifting_it_keeps_the_record(api_client: AsyncClient, session: AsyncSession) -> None:
    shop = await a_live_shop(api_client, session, "keepsrecord")
    _, email, _ = await a_buyer(api_client)
    switch(api_client, shop.seller)
    created = await shut_out(api_client, email)
    await api_client.post(
        f"{BLOCKED_BUYERS}/{created.json()['id']}/revoke", headers=csrf_headers(api_client)
    )

    body = (await api_client.get(BLOCKED_BUYERS)).json()

    assert body["total"] == 1
    assert body["items"][0]["reason"] == REASON
    assert body["items"][0]["in_force"] is False
    assert body["items"][0]["revoked_at"] is not None


async def test_the_same_buyer_can_be_shut_out_again_as_a_second_record(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    shop = await a_live_shop(api_client, session, "secondtime")
    _, email, _ = await a_buyer(api_client)
    switch(api_client, shop.seller)
    created = await shut_out(api_client, email, reason="Первый раз")
    await api_client.post(
        f"{BLOCKED_BUYERS}/{created.json()['id']}/revoke", headers=csrf_headers(api_client)
    )

    await shut_out(api_client, email, reason="Второй раз")

    body = (await api_client.get(BLOCKED_BUYERS)).json()
    assert [item["reason"] for item in body["items"]] == ["Второй раз", "Первый раз"]


async def test_staff_can_see_which_shops_barred_a_buyer(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    shop = await a_live_shop(api_client, session, "staffsees")
    buyer_id, email, _ = await a_buyer(api_client)
    switch(api_client, shop.seller)
    await shut_out(api_client, email)

    moderator = await seed_staff(session, UserRole.MODERATOR)
    await act_as(api_client, moderator)
    body = (await api_client.get(f"{ACCOUNTS}/{buyer_id}/store-blocks")).json()

    assert body["total"] == 1
    assert body["items"][0]["store_name"] == "Тестовый магазин"


async def test_an_administrator_can_open_a_door_the_seller_closed(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    shop = await a_live_shop(api_client, session, "adminopens")
    _, email, buyer = await a_buyer(api_client)
    switch(api_client, shop.seller)
    created = await shut_out(api_client, email)

    admin = await seed_staff(session, UserRole.ADMIN)
    await act_as(api_client, admin)
    lifted = await api_client.post(
        f"{STORE_BLOCKS}/{created.json()['id']}/revoke", headers=csrf_headers(api_client)
    )

    assert lifted.status_code == 200
    switch(api_client, buyer)
    assert (await api_client.get(f"{STOREFRONT}/{shop.subdomain}")).status_code == 200


async def test_a_moderator_does_not_open_doors(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    shop = await a_live_shop(api_client, session, "notmoderator")
    _, email, _ = await a_buyer(api_client)
    switch(api_client, shop.seller)
    created = await shut_out(api_client, email)

    moderator = await seed_staff(session, UserRole.MODERATOR)
    await act_as(api_client, moderator)
    response = await api_client.post(
        f"{STORE_BLOCKS}/{created.json()['id']}/revoke", headers=csrf_headers(api_client)
    )

    assert response.status_code == 403


async def test_nothing_is_deleted_by_any_of_this(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    shop = await a_live_shop(api_client, session, "nodeletes")
    buyer_id, email, _ = await a_buyer(api_client)
    switch(api_client, shop.seller)
    created = await shut_out(api_client, email)
    await api_client.post(
        f"{BLOCKED_BUYERS}/{created.json()['id']}/revoke", headers=csrf_headers(api_client)
    )

    rows = (await session.execute(select(BusinessCustomerBlock))).scalars().all()
    assert len(rows) == 1
    assert await session.get(User, uuid.UUID(buyer_id)) is not None


async def test_both_decisions_are_journalled(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    shop = await a_live_shop(api_client, session, "journalled")
    _, email, _ = await a_buyer(api_client)
    switch(api_client, shop.seller)
    created = await shut_out(api_client, email)
    await api_client.post(
        f"{BLOCKED_BUYERS}/{created.json()['id']}/revoke", headers=csrf_headers(api_client)
    )

    written = (
        (await session.execute(select(AuditLog).order_by(AuditLog.created_at))).scalars().all()
    )
    actions = [entry.action for entry in written]
    assert actions[-2:] == ["store.customer_blocked", "store.customer_unblocked"]
    assert written[-2].details == {"buyer": email}


async def test_opening_a_door_that_is_already_open_is_refused(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    shop = await a_live_shop(api_client, session, "alreadyopen")
    _, email, _ = await a_buyer(api_client)
    switch(api_client, shop.seller)
    created = await shut_out(api_client, email)
    block_id = created.json()["id"]
    await api_client.post(f"{BLOCKED_BUYERS}/{block_id}/revoke", headers=csrf_headers(api_client))

    response = await api_client.post(
        f"{BLOCKED_BUYERS}/{block_id}/revoke", headers=csrf_headers(api_client)
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "block_not_found"
