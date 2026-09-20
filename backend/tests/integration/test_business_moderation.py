import uuid
from typing import Any

import pytest
from httpx import AsyncClient, Response
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import BusinessDecision, BusinessModerationReview
from tests.integration.conftest import (
    become_moderator,
    csrf_headers,
    register_buyer,
    register_seller,
)

pytestmark = pytest.mark.integration

QUEUE_URL = "/api/v1/moderation/businesses"
STORES_URL = "/api/v1/stores"
REASON = "Юридическое название не совпадает с документами"


def action_url(business_id: str, action: str) -> str:
    return f"{QUEUE_URL}/{business_id}/{action}"


async def a_seller_awaiting_admission(client: AsyncClient, subdomain: str | None = None) -> str:
    """Registers a seller, optionally with a storefront. Leaves the client logged in as them."""
    registered = await register_seller(client, email=f"seller-{uuid.uuid4().hex}@example.com")
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
    first = await a_seller_awaiting_admission(api_client)
    second = await a_seller_awaiting_admission(api_client)
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
    await a_seller_awaiting_admission(api_client, subdomain="cups")
    await become_moderator(api_client, session)

    item = (await api_client.get(QUEUE_URL)).json()["items"][0]

    assert item["subdomain"] == "cups"
    assert item["store_status"] == "draft"


async def test_admission_puts_the_storefront_on_the_air(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    """The point of the whole task: until this happens the subdomain answers 404."""
    business_id = await a_seller_awaiting_admission(api_client, subdomain="cups")
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
    business_id = await a_seller_awaiting_admission(api_client)
    await become_moderator(api_client, session)

    approved = await act(api_client, business_id, "approve")

    assert approved.status_code == 200
    assert approved.json()["subdomain"] is None
    assert approved.json()["store_status"] is None


async def test_a_storefront_created_after_admission_is_live_at_once(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    """Otherwise it would sit in draft waiting for a moderation event that never comes."""
    business_id = await a_seller_awaiting_admission(api_client)
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
    business_id = await a_seller_awaiting_admission(api_client)
    await become_moderator(api_client, session)
    assert (await act(api_client, business_id, "approve")).status_code == 200

    response = await act(api_client, business_id, "approve")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "invalid_transition"


async def test_suspension_takes_the_storefront_off_the_air(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    business_id = await a_seller_awaiting_admission(api_client, subdomain="cups")
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
    business_id = await a_seller_awaiting_admission(api_client, subdomain="cups")
    await become_moderator(api_client, session)
    await act(api_client, business_id, "approve")

    blocked = await act(api_client, business_id, "block", reason=REASON)

    assert blocked.json()["status"] == "blocked"
    assert blocked.json()["store_status"] == "blocked"
    assert (await storefront(api_client, "cups")).status_code == 404


async def test_a_ban_can_be_taken_back(api_client: AsyncClient, session: AsyncSession) -> None:
    """A ban is a status, not a deletion."""
    business_id = await a_seller_awaiting_admission(api_client, subdomain="cups")
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
    business_id = await a_seller_awaiting_admission(api_client)
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
    business_id = await a_seller_awaiting_admission(api_client)
    await become_moderator(api_client, session)

    response = await act(api_client, business_id, "suspend", reason=REASON)

    assert response.status_code == 409


async def test_a_blocked_seller_is_not_blocked_twice(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    business_id = await a_seller_awaiting_admission(api_client)
    await become_moderator(api_client, session)
    await act(api_client, business_id, "block", reason=REASON)

    response = await act(api_client, business_id, "block", reason=REASON)

    assert response.status_code == 409


async def test_there_is_nothing_to_restore_in_an_active_seller(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    business_id = await a_seller_awaiting_admission(api_client)
    await become_moderator(api_client, session)
    await act(api_client, business_id, "approve")

    response = await act(api_client, business_id, "restore")

    assert response.status_code == 409


async def test_an_admitted_seller_leaves_the_queue(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    business_id = await a_seller_awaiting_admission(api_client)
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


async def test_a_seller_cannot_admit_themselves(api_client: AsyncClient) -> None:
    business_id = await a_seller_awaiting_admission(api_client)

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
    business_id = await a_seller_awaiting_admission(api_client)
    await become_moderator(api_client, session)

    response = await api_client.post(action_url(business_id, "approve"))

    assert response.status_code == 403
