import uuid
from typing import Any

import pytest
from httpx import AsyncClient, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models import Report, ReportStatus, User, UserRole, UserStatus
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
from tests.integration.test_catalog import (
    CATALOG_PRODUCTS,
)

pytestmark = pytest.mark.integration

REPORTS = "/api/v1/reports"
QUEUE = "/api/v1/moderation/reports"
STOREFRONT = "/api/v1/storefront"
REASON = "Продаёт подделку под видом оригинала"


async def complain(client: AsyncClient, **body: Any) -> Response:
    """No CSRF header on purpose: a guest has no CSRF cookie to echo."""
    return await client.post(REPORTS, json=body)


async def resolve(
    client: AsyncClient, subject: str, subject_id: str, action: str, reason: str = REASON
) -> Response:
    return await client.post(
        f"{QUEUE}/{subject}/{subject_id}/{action}",
        json={"reason": reason},
        headers=csrf_headers(client),
    )


async def rows(session: AsyncSession) -> list[Report]:
    result = await session.execute(select(Report).order_by(Report.created_at))
    return list(result.scalars().all())


async def queue_of(client: AsyncClient) -> dict[str, Any]:
    response = await client.get(QUEUE)
    assert response.status_code == 200
    body: dict[str, Any] = response.json()
    return body


async def test_a_guest_complains_about_a_product(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    """Someone who has just been cheated is not going to register first."""
    shop = await a_live_shop(api_client, session, "cups")
    product_id = await a_published_product(api_client, session, shop)
    await anonymous(api_client)

    response = await complain(api_client, product_id=product_id, reason=REASON)

    assert response.status_code == 201
    written = await rows(session)
    assert len(written) == 1
    assert written[0].reporter_user_id is None
    assert written[0].status is ReportStatus.OPEN


async def test_a_guest_complains_about_a_shop(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    await a_live_shop(api_client, session, "cups")
    await anonymous(api_client)

    response = await complain(api_client, subdomain="cups", reason=REASON)

    assert response.status_code == 201
    assert (await rows(session))[0].business_id is not None


async def test_the_complaint_of_a_guest_reaches_the_queue(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    shop = await a_live_shop(api_client, session, "cups")
    product_id = await a_published_product(api_client, session, shop)
    await anonymous(api_client)
    await complain(api_client, product_id=product_id, reason=REASON)

    switch(api_client, shop.moderator)
    body = await queue_of(api_client)

    assert body["total"] == 1
    assert body["items"][0]["product"]["id"] == product_id
    assert body["items"][0]["reasons"] == [REASON]


async def test_a_signed_in_buyer_complains_too(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    shop = await a_live_shop(api_client, session, "cups")
    product_id = await a_published_product(api_client, session, shop)
    api_client.cookies.clear()
    await register_buyer(api_client, email=f"buyer-{uuid.uuid4().hex}@example.com")

    await complain(api_client, product_id=product_id, reason=REASON)

    assert (await rows(session))[0].reporter_user_id is not None


async def test_the_same_person_complaining_twice_is_one_complaint(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    shop = await a_live_shop(api_client, session, "cups")
    product_id = await a_published_product(api_client, session, shop)
    api_client.cookies.clear()
    await register_buyer(api_client, email=f"buyer-{uuid.uuid4().hex}@example.com")

    first = await complain(api_client, product_id=product_id, reason=REASON)
    second = await complain(api_client, product_id=product_id, reason="И ещё раз")

    assert first.json()["id"] == second.json()["id"]
    assert len(await rows(session)) == 1


async def test_many_complaints_about_one_product_are_one_line(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    """Twenty people reporting one product must not become twenty lines to click through."""
    shop = await a_live_shop(api_client, session, "cups")
    product_id = await a_published_product(api_client, session, shop)
    await anonymous(api_client)
    for index in range(3):
        await complain(api_client, product_id=product_id, reason=f"Жалоба {index}")

    switch(api_client, shop.moderator)
    body = await queue_of(api_client)

    assert body["total"] == 1
    assert body["items"][0]["total"] == 3
    # newest first, so the freshest wording is the one a moderator reads
    assert body["items"][0]["reasons"][0] == "Жалоба 2"


async def test_a_complaint_needs_exactly_one_subject(api_client: AsyncClient) -> None:
    assert (await complain(api_client, reason=REASON)).status_code == 422
    assert (
        await complain(api_client, product_id=str(uuid.uuid4()), subdomain="cups", reason=REASON)
    ).status_code == 422


async def test_a_complaint_needs_a_reason(api_client: AsyncClient, session: AsyncSession) -> None:
    shop = await a_live_shop(api_client, session, "cups")
    product_id = await a_published_product(api_client, session, shop)
    await anonymous(api_client)

    assert (await complain(api_client, product_id=product_id, reason="   ")).status_code == 422


async def test_nothing_the_visitor_cannot_see_may_be_reported(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    """A product already off the shelf and one that never existed answer the same."""
    await anonymous(api_client)

    response = await complain(api_client, product_id=str(uuid.uuid4()), reason=REASON)

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "report_subject_not_found"


async def test_a_hidden_product_cannot_be_reported(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    shop = await a_live_shop(api_client, session, "cups")
    product_id = await a_published_product(api_client, session, shop)
    switch(api_client, shop.moderator)
    await api_client.post(
        f"/api/v1/moderation/products/{product_id}/hide", headers=csrf_headers(api_client)
    )
    await anonymous(api_client)

    assert (await complain(api_client, product_id=product_id, reason=REASON)).status_code == 404


async def test_upholding_takes_the_product_off_the_shelf(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    shop = await a_live_shop(api_client, session, "cups")
    product_id = await a_published_product(api_client, session, shop)
    await anonymous(api_client)
    await complain(api_client, product_id=product_id, reason=REASON)
    switch(api_client, shop.moderator)

    response = await resolve(api_client, "product", product_id, "uphold")

    assert response.status_code == 200
    assert response.json()["closed"] == 1
    await anonymous(api_client)
    assert (await api_client.get(f"{CATALOG_PRODUCTS}/{product_id}")).status_code == 404


async def test_upholding_takes_the_shop_off_the_air(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    shop = await a_live_shop(api_client, session, "cups")
    await a_published_product(api_client, session, shop)
    await anonymous(api_client)
    await complain(api_client, subdomain="cups", reason=REASON)
    switch(api_client, shop.moderator)

    assert (await resolve(api_client, "business", shop.business_id, "uphold")).status_code == 200

    await anonymous(api_client)
    assert (await api_client.get(f"{STOREFRONT}/cups")).status_code == 404


async def test_a_verdict_lands_in_the_same_moderation_history(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    """The seller reads it where they read every other verdict, not in a separate place."""
    from app.models import ModerationDecision, ModerationReview

    shop = await a_live_shop(api_client, session, "cups")
    product_id = await a_published_product(api_client, session, shop)
    await anonymous(api_client)
    await complain(api_client, product_id=product_id, reason=REASON)
    switch(api_client, shop.moderator)
    await resolve(api_client, "product", product_id, "uphold")

    result = await session.execute(
        select(ModerationReview).where(ModerationReview.product_id == uuid.UUID(product_id))
    )
    assert ModerationDecision.HIDDEN in [review.decision for review in result.scalars().all()]


async def test_one_verdict_closes_every_complaint_about_the_subject(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    shop = await a_live_shop(api_client, session, "cups")
    product_id = await a_published_product(api_client, session, shop)
    await anonymous(api_client)
    for index in range(3):
        await complain(api_client, product_id=product_id, reason=f"Жалоба {index}")
    switch(api_client, shop.moderator)

    response = await resolve(api_client, "product", product_id, "uphold")

    assert response.json()["closed"] == 3
    assert (await queue_of(api_client))["total"] == 0


async def test_a_closed_complaint_leaves_the_queue_and_stays_in_history(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    shop = await a_live_shop(api_client, session, "cups")
    product_id = await a_published_product(api_client, session, shop)
    await anonymous(api_client)
    await complain(api_client, product_id=product_id, reason=REASON)
    switch(api_client, shop.moderator)

    await resolve(api_client, "product", product_id, "dismiss", reason="Проверили, всё честно")

    assert (await queue_of(api_client))["total"] == 0
    written = await rows(session)
    assert len(written) == 1
    assert written[0].status is ReportStatus.DISMISSED
    assert written[0].resolution_reason == "Проверили, всё честно"
    assert written[0].resolved_at is not None
    assert written[0].resolved_by is not None


async def test_a_dismissal_leaves_the_product_where_it_was(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    shop = await a_live_shop(api_client, session, "cups")
    product_id = await a_published_product(api_client, session, shop)
    await anonymous(api_client)
    await complain(api_client, product_id=product_id, reason=REASON)
    switch(api_client, shop.moderator)

    await resolve(api_client, "product", product_id, "dismiss", reason="Ничего не нашли")

    await anonymous(api_client)
    assert (await api_client.get(f"{CATALOG_PRODUCTS}/{product_id}")).status_code == 200


async def test_a_dismissal_without_a_reason_is_refused(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    """Nothing happens to the subject, so the reason is the only record of the decision."""
    shop = await a_live_shop(api_client, session, "cups")
    product_id = await a_published_product(api_client, session, shop)
    await anonymous(api_client)
    await complain(api_client, product_id=product_id, reason=REASON)
    switch(api_client, shop.moderator)

    assert (
        await resolve(api_client, "product", product_id, "dismiss", reason="  ")
    ).status_code == 422


async def test_resolving_what_nobody_reported_is_refused(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    shop = await a_live_shop(api_client, session, "cups")
    product_id = await a_published_product(api_client, session, shop)
    switch(api_client, shop.moderator)

    response = await resolve(api_client, "product", product_id, "uphold")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "no_open_reports"


async def test_a_complaint_filed_after_a_verdict_opens_a_new_line(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    shop = await a_live_shop(api_client, session, "cups")
    product_id = await a_published_product(api_client, session, shop)
    await anonymous(api_client)
    await complain(api_client, product_id=product_id, reason=REASON)
    switch(api_client, shop.moderator)
    await resolve(api_client, "product", product_id, "dismiss", reason="Ничего не нашли")
    await anonymous(api_client)

    await complain(api_client, product_id=product_id, reason="Снова то же самое")

    switch(api_client, shop.moderator)
    assert (await queue_of(api_client))["total"] == 1
    assert len(await rows(session)) == 2


@pytest.mark.parametrize("role", [UserRole.BUYER, UserRole.SELLER])
async def test_nobody_below_a_moderator_sees_the_queue(
    api_client: AsyncClient, session: AsyncSession, role: UserRole
) -> None:
    if role is UserRole.BUYER:
        api_client.cookies.clear()
        await register_buyer(api_client, email=f"buyer-{uuid.uuid4().hex}@example.com")
    else:
        await act_as(api_client, await seed_staff(session, role))

    assert (await api_client.get(QUEUE)).status_code == 403


async def test_an_anonymous_visitor_does_not_see_the_queue(api_client: AsyncClient) -> None:
    assert (await api_client.get(QUEUE)).status_code == 401


async def test_resolving_without_the_csrf_header_is_forbidden(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    shop = await a_live_shop(api_client, session, "cups")
    product_id = await a_published_product(api_client, session, shop)
    switch(api_client, shop.moderator)

    response = await api_client.post(
        f"{QUEUE}/product/{product_id}/uphold", json={"reason": REASON}
    )

    assert response.status_code == 403


async def test_an_unknown_subject_kind_is_not_a_route(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    await act_as(api_client, await seed_staff(session, UserRole.MODERATOR))

    response = await api_client.post(
        f"{QUEUE}/seller/{uuid.uuid4()}/uphold",
        json={"reason": REASON},
        headers=csrf_headers(api_client),
    )

    assert response.status_code == 422


async def test_the_reporter_learns_nothing_about_the_outcome(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    """The answer carries an identifier and nothing else: how many others complained and
    what a moderator decided are not the reporter's business."""
    shop = await a_live_shop(api_client, session, "cups")
    product_id = await a_published_product(api_client, session, shop)
    await anonymous(api_client)

    body = (await complain(api_client, product_id=product_id, reason=REASON)).json()

    assert set(body) == {"id"}


async def test_a_stale_session_complains_as_a_guest(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    """A broken cookie must not swallow the complaint — the person still gets to be heard."""
    shop = await a_live_shop(api_client, session, "cups")
    product_id = await a_published_product(api_client, session, shop)
    await anonymous(api_client)
    api_client.cookies.set(get_settings().access_cookie_name, "not-a-token")

    response = await complain(api_client, product_id=product_id, reason=REASON)

    assert response.status_code == 201
    assert (await rows(session))[0].reporter_user_id is None


async def test_a_barred_account_complains_as_a_guest(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    shop = await a_live_shop(api_client, session, "cups")
    product_id = await a_published_product(api_client, session, shop)
    api_client.cookies.clear()
    registered = await register_buyer(api_client, email=f"buyer-{uuid.uuid4().hex}@example.com")
    buyer = await session.get(User, uuid.UUID(registered.json()["id"]))
    assert buyer is not None
    buyer.status = UserStatus.BLOCKED
    await session.flush()

    response = await complain(api_client, product_id=product_id, reason=REASON)

    assert response.status_code == 201
    assert (await rows(session))[0].reporter_user_id is None


async def test_a_shop_that_is_not_on_the_air_cannot_be_reported(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    await anonymous(api_client)

    response = await complain(api_client, subdomain="nosuchshop", reason=REASON)

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "report_subject_not_found"


async def test_a_complaint_about_a_shop_is_dismissed_with_a_reason(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    shop = await a_live_shop(api_client, session, "cups")
    await anonymous(api_client)
    await complain(api_client, subdomain="cups", reason=REASON)
    switch(api_client, shop.moderator)

    response = await resolve(
        api_client, "business", shop.business_id, "dismiss", reason="Проверили, всё в порядке"
    )

    assert response.json()["closed"] == 1
    assert (await queue_of(api_client))["total"] == 0
    await anonymous(api_client)
    # the shop stays on the air: nothing was found against it
    assert (await api_client.get(f"{STOREFRONT}/cups")).status_code == 200


async def test_the_queue_shows_the_shop_a_complaint_is_about(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    shop = await a_live_shop(api_client, session, "cups")
    await anonymous(api_client)
    await complain(api_client, subdomain="cups", reason=REASON)
    switch(api_client, shop.moderator)

    item = (await queue_of(api_client))["items"][0]

    assert item["product"] is None
    assert item["shop"] == {"display_name": "Тестовый магазин", "subdomain": "cups"}
