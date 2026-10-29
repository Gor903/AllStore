import uuid
from typing import Any

import pytest
from httpx import AsyncClient, Response
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog, BusinessDecision, BusinessModerationReview
from tests.integration.conftest import (
    anonymous,
    become_moderator,
    create_product,
    csrf_headers,
    register_buyer,
    register_seller,
    seeded_category,
    switch,
)

pytestmark = pytest.mark.integration

QUEUE_URL = "/api/v1/moderation/businesses"
STORES_URL = "/api/v1/stores"
REASON = "Юридическое название не совпадает с документами"


def action_url(business_id: str, action: str) -> str:
    return f"{QUEUE_URL}/{business_id}/{action}"


async def a_seller_awaiting_admission(
    client: AsyncClient, session: AsyncSession, subdomain: str | None = None
) -> str:
    """Registers a seller, optionally with a storefront. Leaves the client logged in as them."""
    registered = await register_seller(
        client, session, email=f"seller-{uuid.uuid4().hex}@example.com"
    )
    if subdomain is not None:
        created = await client.post(
            STORES_URL, json={"subdomain": subdomain}, headers=csrf_headers(client)
        )
        assert created.status_code == 201
    return str(registered.json()["business"]["id"])


async def act(client: AsyncClient, business_id: str, action: str, **body: Any) -> Response:
    return await client.post(
        action_url(business_id, action), json=body or None, headers=csrf_headers(client)
    )


async def reviews_of(session: AsyncSession, business_id: str) -> list[BusinessModerationReview]:
    result = await session.execute(
        select(BusinessModerationReview)
        .where(BusinessModerationReview.business_id == uuid.UUID(business_id))
        .order_by(BusinessModerationReview.created_at)
    )
    return list(result.scalars())


async def storefront(client: AsyncClient, subdomain: str) -> Response:
    return await client.get(f"/api/v1/storefront/{subdomain}")


async def test_the_queue_holds_sellers_awaiting_admission(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    first = await a_seller_awaiting_admission(api_client, session)
    second = await a_seller_awaiting_admission(api_client, session)
    # now() is the start of the transaction, so the wait is set apart by hand
    await session.execute(
        text("UPDATE businesses SET created_at = now() - interval '1 hour' WHERE id = :id"),
        {"id": uuid.UUID(first)},
    )
    await become_moderator(api_client, session)

    response = await api_client.get(QUEUE_URL)

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert [item["id"] for item in body["items"]] == [first, second]


async def test_the_queue_carries_the_storefront_address(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    await a_seller_awaiting_admission(api_client, session, subdomain="cups")
    await become_moderator(api_client, session)

    item = (await api_client.get(QUEUE_URL)).json()["items"][0]

    assert item["subdomain"] == "cups"
    assert item["store_status"] == "draft"


async def test_admission_puts_the_storefront_on_the_air(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    """The point of the whole task: until this happens the subdomain answers 404."""
    business_id = await a_seller_awaiting_admission(api_client, session, subdomain="cups")
    assert (await storefront(api_client, "cups")).status_code == 404
    moderator = await become_moderator(api_client, session)

    approved = await act(api_client, business_id, "approve")

    assert approved.status_code == 200
    assert approved.json()["status"] == "active"
    assert approved.json()["store_status"] == "active"
    live = await storefront(api_client, "cups")
    assert live.status_code == 200
    assert live.json()["subdomain"] == "cups"
    reviews = await reviews_of(session, business_id)
    assert [review.decision for review in reviews] == [BusinessDecision.APPROVED]
    assert reviews[0].moderator_id == moderator.id


async def test_a_seller_without_a_storefront_is_admitted_all_the_same(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    business_id = await a_seller_awaiting_admission(api_client, session)
    await become_moderator(api_client, session)

    approved = await act(api_client, business_id, "approve")

    assert approved.status_code == 200
    assert approved.json()["subdomain"] is None
    assert approved.json()["store_status"] is None


async def test_a_storefront_created_after_admission_is_live_at_once(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    """Otherwise it would sit in draft waiting for a moderation event that never comes."""
    business_id = await a_seller_awaiting_admission(api_client, session)
    seller_cookies = dict(api_client.cookies)
    await become_moderator(api_client, session)
    assert (await act(api_client, business_id, "approve")).status_code == 200

    api_client.cookies.clear()
    api_client.cookies.update(seller_cookies)
    created = await api_client.post(
        STORES_URL, json={"subdomain": "mugs"}, headers=csrf_headers(api_client)
    )

    assert created.json()["status"] == "active"
    assert (await storefront(api_client, "mugs")).status_code == 200


async def test_a_seller_is_admitted_only_once(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    business_id = await a_seller_awaiting_admission(api_client, session)
    await become_moderator(api_client, session)
    assert (await act(api_client, business_id, "approve")).status_code == 200

    response = await act(api_client, business_id, "approve")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "invalid_transition"


async def test_suspension_takes_the_storefront_off_the_air(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    business_id = await a_seller_awaiting_admission(api_client, session, subdomain="cups")
    await become_moderator(api_client, session)
    await act(api_client, business_id, "approve")

    suspended = await act(api_client, business_id, "suspend", reason=f"  {REASON}  ")

    assert suspended.json()["status"] == "suspended"
    assert suspended.json()["store_status"] == "suspended"
    assert (await storefront(api_client, "cups")).status_code == 404
    assert (await reviews_of(session, business_id))[1].reason == REASON


async def test_a_blocked_seller_disappears_from_the_public_side(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    business_id = await a_seller_awaiting_admission(api_client, session, subdomain="cups")
    await become_moderator(api_client, session)
    await act(api_client, business_id, "approve")

    blocked = await act(api_client, business_id, "block", reason=REASON)

    assert blocked.json()["status"] == "blocked"
    assert blocked.json()["store_status"] == "blocked"
    assert (await storefront(api_client, "cups")).status_code == 404


async def test_a_ban_can_be_taken_back(api_client: AsyncClient, session: AsyncSession) -> None:
    """A ban is a status, not a deletion."""
    business_id = await a_seller_awaiting_admission(api_client, session, subdomain="cups")
    await become_moderator(api_client, session)
    await act(api_client, business_id, "approve")
    await act(api_client, business_id, "block", reason=REASON)

    restored = await act(api_client, business_id, "restore")

    assert restored.json()["status"] == "active"
    assert restored.json()["store_status"] == "active"
    assert (await storefront(api_client, "cups")).status_code == 200
    assert [review.decision for review in await reviews_of(session, business_id)] == [
        BusinessDecision.APPROVED,
        BusinessDecision.BLOCKED,
        BusinessDecision.RESTORED,
    ]


@pytest.mark.parametrize("action", ["suspend", "block"])
@pytest.mark.parametrize("body", [{}, {"reason": ""}, {"reason": "   "}])
async def test_a_seller_is_not_taken_off_the_air_without_a_reason(
    api_client: AsyncClient, session: AsyncSession, action: str, body: dict[str, Any]
) -> None:
    business_id = await a_seller_awaiting_admission(api_client, session)
    await become_moderator(api_client, session)
    await act(api_client, business_id, "approve")

    response = await api_client.post(
        action_url(business_id, action), json=body, headers=csrf_headers(api_client)
    )

    assert response.status_code == 422
    assert len(await reviews_of(session, business_id)) == 1


async def test_an_applicant_is_not_suspended_before_being_admitted(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    business_id = await a_seller_awaiting_admission(api_client, session)
    await become_moderator(api_client, session)

    response = await act(api_client, business_id, "suspend", reason=REASON)

    assert response.status_code == 409


async def test_a_blocked_seller_is_not_blocked_twice(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    business_id = await a_seller_awaiting_admission(api_client, session)
    await become_moderator(api_client, session)
    await act(api_client, business_id, "block", reason=REASON)

    response = await act(api_client, business_id, "block", reason=REASON)

    assert response.status_code == 409


async def test_there_is_nothing_to_restore_in_an_active_seller(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    business_id = await a_seller_awaiting_admission(api_client, session)
    await become_moderator(api_client, session)
    await act(api_client, business_id, "approve")

    response = await act(api_client, business_id, "restore")

    assert response.status_code == 409


async def test_an_admitted_seller_leaves_the_queue(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    business_id = await a_seller_awaiting_admission(api_client, session)
    await become_moderator(api_client, session)
    await act(api_client, business_id, "approve")

    assert (await api_client.get(QUEUE_URL)).json()["total"] == 0


async def test_an_unknown_business_is_not_found(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    await become_moderator(api_client, session)

    response = await act(api_client, str(uuid.uuid4()), "approve")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "business_not_found"


async def test_a_seller_cannot_admit_themselves(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    business_id = await a_seller_awaiting_admission(api_client, session)

    response = await act(api_client, business_id, "approve")

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "permission_denied"


async def test_a_buyer_cannot_see_the_queue(api_client: AsyncClient) -> None:
    await register_buyer(api_client)

    assert (await api_client.get(QUEUE_URL)).status_code == 403


async def test_an_anonymous_visitor_cannot_see_the_queue(api_client: AsyncClient) -> None:
    assert (await api_client.get(QUEUE_URL)).status_code == 401


async def test_a_decision_without_the_csrf_header_is_forbidden(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    business_id = await a_seller_awaiting_admission(api_client, session)
    await become_moderator(api_client, session)

    response = await api_client.post(action_url(business_id, "approve"))

    assert response.status_code == 403


# Этап 18: a refusal is a verdict an applicant can answer, which is what makes it different
# from a ban. Everything below turns on that difference.

MY_BUSINESS = "/api/v1/users/me/business"
PRODUCTS_URL = "/api/v1/products"


async def my_business(client: AsyncClient) -> dict[str, Any]:
    response = await client.get(MY_BUSINESS)
    assert response.status_code == 200
    return dict(response.json())


async def test_an_applicant_is_refused_with_a_reason(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    business_id = await a_seller_awaiting_admission(api_client, session, "refused")
    seller = dict(api_client.cookies)
    await become_moderator(api_client, session)

    response = await act(api_client, business_id, "reject", reason=REASON)

    assert response.status_code == 200
    assert response.json()["status"] == "rejected"
    switch(api_client, seller)
    assert (await my_business(api_client))["status_reason"] == REASON


async def test_a_refusal_without_a_reason_is_itself_refused(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    """A refusal the applicant cannot act on is not a refusal."""
    business_id = await a_seller_awaiting_admission(api_client, session)
    await become_moderator(api_client, session)

    assert (await act(api_client, business_id, "reject", reason="   ")).status_code == 422


async def test_a_refused_shop_is_not_on_the_air(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    business_id = await a_seller_awaiting_admission(api_client, session, "notonair")
    await become_moderator(api_client, session)

    await act(api_client, business_id, "reject", reason=REASON)

    await anonymous(api_client)
    assert (await storefront(api_client, "notonair")).status_code == 404


async def test_only_an_applicant_is_refused(api_client: AsyncClient, session: AsyncSession) -> None:
    """An admitted shop is suspended or barred; those are verdicts with their own words."""
    business_id = await a_seller_awaiting_admission(api_client, session, "alreadyin")
    await become_moderator(api_client, session)
    await act(api_client, business_id, "approve")

    response = await act(api_client, business_id, "reject", reason=REASON)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "invalid_transition"


async def test_the_applicant_answers_the_refusal_and_waits_again(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    business_id = await a_seller_awaiting_admission(api_client, session, "answers")
    seller = dict(api_client.cookies)
    await become_moderator(api_client, session)
    await act(api_client, business_id, "reject", reason=REASON)

    switch(api_client, seller)
    response = await api_client.post(f"{MY_BUSINESS}/resubmit", headers=csrf_headers(api_client))

    assert response.status_code == 200
    assert response.json()["status"] == "pending"


async def test_answering_a_refusal_keeps_every_verdict(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    business_id = await a_seller_awaiting_admission(api_client, session)
    seller = dict(api_client.cookies)
    await become_moderator(api_client, session)
    await act(api_client, business_id, "reject", reason=REASON)

    switch(api_client, seller)
    await api_client.post(f"{MY_BUSINESS}/resubmit", headers=csrf_headers(api_client))

    history = await reviews_of(session, business_id)
    assert [review.decision for review in history] == [
        BusinessDecision.REJECTED,
        BusinessDecision.RESUBMITTED,
    ]
    assert history[0].reason == REASON


async def test_a_resubmitted_applicant_comes_back_to_the_queue_with_their_history(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    """Somebody refused once and now applying again is not the same case as a fresh applicant."""
    business_id = await a_seller_awaiting_admission(api_client, session)
    seller = dict(api_client.cookies)
    moderator_cookies = None
    await become_moderator(api_client, session)
    moderator_cookies = dict(api_client.cookies)
    await act(api_client, business_id, "reject", reason=REASON)
    switch(api_client, seller)
    await api_client.post(f"{MY_BUSINESS}/resubmit", headers=csrf_headers(api_client))

    switch(api_client, moderator_cookies)
    queued = (await api_client.get(QUEUE_URL)).json()["items"]
    mine = next(item for item in queued if item["id"] == business_id)

    assert [entry["decision"] for entry in mine["history"]] == ["resubmitted", "rejected"]
    assert mine["history"][1]["reason"] == REASON


async def test_nothing_but_a_refusal_can_be_answered(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    business_id = await a_seller_awaiting_admission(api_client, session)
    seller = dict(api_client.cookies)
    await become_moderator(api_client, session)
    await act(api_client, business_id, "approve")

    switch(api_client, seller)
    response = await api_client.post(f"{MY_BUSINESS}/resubmit", headers=csrf_headers(api_client))

    assert response.status_code == 409


async def test_an_applicant_may_fill_the_shelves_while_waiting(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    """Nothing is public until a moderator says so, and a seller who cannot prepare anything
    has nothing to be admitted for."""
    await a_seller_awaiting_admission(api_client, session, "prepares")
    category = await seeded_category(session)

    created = await create_product(api_client, category.id)

    assert created.status_code == 201


@pytest.mark.parametrize(
    ("action", "body"),
    [
        ("reject", {"reason": REASON}),
        ("suspend", {"reason": REASON}),
        ("block", {"reason": REASON}),
    ],
)
async def test_a_shop_under_a_verdict_does_not_queue_new_goods(
    api_client: AsyncClient, session: AsyncSession, action: str, body: dict[str, Any]
) -> None:
    """Otherwise the verdict is something to outlast rather than to answer."""
    business_id = await a_seller_awaiting_admission(api_client, session, f"verdict{action}")
    seller = dict(api_client.cookies)
    category = await seeded_category(session)
    await become_moderator(api_client, session)
    if action != "reject":
        await act(api_client, business_id, "approve")
    await act(api_client, business_id, action, **body)

    switch(api_client, seller)
    created = await create_product(api_client, category.id)

    assert created.status_code == 403
    assert created.json()["error"]["code"] == "business_not_trading"


async def test_a_shop_under_a_verdict_does_not_resubmit_old_goods_either(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    business_id = await a_seller_awaiting_admission(api_client, session, "nosubmit")
    seller = dict(api_client.cookies)
    category = await seeded_category(session)
    product_id = (await create_product(api_client, category.id)).json()["id"]
    await become_moderator(api_client, session)
    await act(api_client, business_id, "reject", reason=REASON)

    switch(api_client, seller)
    response = await api_client.post(
        f"{PRODUCTS_URL}/{product_id}/submit", headers=csrf_headers(api_client)
    )

    assert response.status_code == 403


async def test_a_refused_applicant_cannot_open_a_storefront(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    business_id = await a_seller_awaiting_admission(api_client, session)
    seller = dict(api_client.cookies)
    await become_moderator(api_client, session)
    await act(api_client, business_id, "reject", reason=REASON)

    switch(api_client, seller)
    response = await api_client.post(
        STORES_URL, json={"subdomain": f"s{uuid.uuid4().hex[:8]}"}, headers=csrf_headers(api_client)
    )

    assert response.status_code == 403


async def test_every_verdict_on_a_shop_reaches_the_journal(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    business_id = await a_seller_awaiting_admission(api_client, session, "journal")
    seller = dict(api_client.cookies)
    await become_moderator(api_client, session)
    await act(api_client, business_id, "reject", reason=REASON)
    switch(api_client, seller)
    await api_client.post(f"{MY_BUSINESS}/resubmit", headers=csrf_headers(api_client))
    await become_moderator(api_client, session)
    await act(api_client, business_id, "approve")
    await act(api_client, business_id, "suspend", reason=REASON)
    await act(api_client, business_id, "restore")

    written = (
        (await session.execute(select(AuditLog).order_by(AuditLog.created_at))).scalars().all()
    )
    assert [entry.action for entry in written] == [
        "business.rejected",
        "business.resubmitted",
        "business.approved",
        "business.suspended",
        "business.restored",
    ]
    assert written[0].details == {"reason": REASON}
