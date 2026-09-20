import uuid
from typing import Any

import pytest
from httpx import AsyncClient, Response
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ModerationDecision, ModerationReview
from tests.integration.conftest import (
    PRODUCTS_URL,
    become_moderator,
    create_product,
    csrf_headers,
    register_buyer,
    register_seller,
    seeded_category,
)

pytestmark = pytest.mark.integration

QUEUE_URL = "/api/v1/moderation/products"
REASON = "Фото не соответствует товару"


def decision_url(product_id: str, action: str) -> str:
    return f"{QUEUE_URL}/{product_id}/{action}"


async def a_product_awaiting_review(
    client: AsyncClient, session: AsyncSession, **fields: Any
) -> str:
    """Leaves the client logged in as the seller who owns it."""
    await register_seller(client, email=f"seller-{uuid.uuid4().hex}@example.com")
    category = await seeded_category(session)
    return str((await create_product(client, category.id, **fields)).json()["id"])


async def decide(client: AsyncClient, product_id: str, action: str, **body: Any) -> Response:
    return await client.post(
        decision_url(product_id, action), json=body or None, headers=csrf_headers(client)
    )


async def reviews_of(session: AsyncSession, product_id: str) -> list[ModerationReview]:
    result = await session.execute(
        select(ModerationReview)
        .where(ModerationReview.product_id == uuid.UUID(product_id))
        .order_by(ModerationReview.created_at)
    )
    return list(result.scalars())


async def test_the_queue_holds_products_awaiting_review(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    first = await a_product_awaiting_review(api_client, session, name="Первый")
    second = await a_product_awaiting_review(api_client, session, name="Второй")
    # now() is the start of the transaction, so rows written inside one test share a timestamp;
    # the wait is set apart by hand to check the order rather than the tie-break on id
    await session.execute(
        text("UPDATE products SET created_at = now() - interval '1 hour' WHERE id = :id"),
        {"id": uuid.UUID(first)},
    )
    await become_moderator(api_client, session)

    response = await api_client.get(QUEUE_URL)

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    # oldest first: whoever has waited longest is looked at first
    assert [item["id"] for item in body["items"]] == [first, second]


async def test_the_queue_crosses_tenants(api_client: AsyncClient, session: AsyncSession) -> None:
    """The one role the isolation rule does not bind — a moderator sees every seller's work."""
    await a_product_awaiting_review(api_client, session, name="Товар А")
    await a_product_awaiting_review(api_client, session, name="Товар Б")
    await become_moderator(api_client, session)

    items = (await api_client.get(QUEUE_URL)).json()["items"]

    assert len({item["business_id"] for item in items}) == 2


async def test_a_decided_product_leaves_the_queue(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    product_id = await a_product_awaiting_review(api_client, session)
    await become_moderator(api_client, session)
    assert (await decide(api_client, product_id, "approve")).status_code == 200

    assert (await api_client.get(QUEUE_URL)).json()["total"] == 0


async def test_an_archived_product_is_not_reviewed(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    product_id = await a_product_awaiting_review(api_client, session)
    await api_client.delete(f"{PRODUCTS_URL}/{product_id}", headers=csrf_headers(api_client))
    await become_moderator(api_client, session)

    assert (await api_client.get(QUEUE_URL)).json()["total"] == 0
    assert (await decide(api_client, product_id, "approve")).status_code == 404


async def test_approval_puts_the_product_on_the_shelf(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    product_id = await a_product_awaiting_review(api_client, session)
    moderator = await become_moderator(api_client, session)

    response = await decide(api_client, product_id, "approve")

    body = response.json()
    assert body["moderation_status"] == "approved"
    assert body["publication_status"] == "published"
    reviews = await reviews_of(session, product_id)
    assert [review.decision for review in reviews] == [ModerationDecision.APPROVED]
    assert reviews[0].moderator_id == moderator.id


async def test_a_verdict_is_passed_only_once(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    product_id = await a_product_awaiting_review(api_client, session)
    await become_moderator(api_client, session)
    assert (await decide(api_client, product_id, "approve")).status_code == 200

    response = await decide(api_client, product_id, "reject", reason=REASON)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "invalid_transition"


async def test_a_refusal_carries_its_reason_to_the_seller(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    product_id = await a_product_awaiting_review(api_client, session)
    await become_moderator(api_client, session)
    refused = await decide(api_client, product_id, "reject", reason=f"  {REASON}  ")

    assert refused.status_code == 200
    assert refused.json()["moderation_status"] == "rejected"
    assert refused.json()["publication_status"] == "draft"
    # the reason is trimmed on the way in and read back out of the verdict that carries it
    assert refused.json()["rejection_reason"] == REASON
    assert (await reviews_of(session, product_id))[0].reason == REASON


@pytest.mark.parametrize("body", [{}, {"reason": ""}, {"reason": "   "}, {"reason": "к" * 1001}])
async def test_a_refusal_without_a_usable_reason_is_refused(
    api_client: AsyncClient, session: AsyncSession, body: dict[str, Any]
) -> None:
    product_id = await a_product_awaiting_review(api_client, session)
    await become_moderator(api_client, session)

    response = await api_client.post(
        decision_url(product_id, "reject"), json=body, headers=csrf_headers(api_client)
    )

    assert response.status_code == 422
    assert (await reviews_of(session, product_id)) == []


async def test_a_rejected_product_returns_to_the_queue_after_a_fix(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    await register_seller(api_client)
    category = await seeded_category(session)
    product_id = str((await create_product(api_client, category.id)).json()["id"])
    seller_cookies = dict(api_client.cookies)
    await become_moderator(api_client, session)
    await decide(api_client, product_id, "reject", reason=REASON)

    api_client.cookies.clear()
    api_client.cookies.update(seller_cookies)
    seen = await api_client.get(f"{PRODUCTS_URL}/{product_id}")
    await api_client.patch(
        f"{PRODUCTS_URL}/{product_id}",
        json={"name": "Исправленное название"},
        headers=csrf_headers(api_client),
    )
    resubmitted = await api_client.post(
        f"{PRODUCTS_URL}/{product_id}/submit", headers=csrf_headers(api_client)
    )

    assert seen.json()["rejection_reason"] == REASON
    assert resubmitted.status_code == 200
    assert resubmitted.json()["moderation_status"] == "pending"
    # the refusal no longer stands, so there is nothing for the seller to act on
    assert resubmitted.json()["rejection_reason"] is None
    # the history keeps the refusal even though the product moved on
    assert [review.decision for review in await reviews_of(session, product_id)] == [
        ModerationDecision.REJECTED
    ]


async def test_a_product_already_in_the_queue_is_not_resubmitted(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    await register_seller(api_client)
    category = await seeded_category(session)
    product_id = (await create_product(api_client, category.id)).json()["id"]

    response = await api_client.post(
        f"{PRODUCTS_URL}/{product_id}/submit", headers=csrf_headers(api_client)
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "invalid_transition"


async def test_a_published_product_is_hidden_and_put_back(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    product_id = await a_product_awaiting_review(api_client, session)
    await become_moderator(api_client, session)
    await decide(api_client, product_id, "approve")

    hidden = await decide(api_client, product_id, "hide")
    restored = await decide(api_client, product_id, "publish")

    assert hidden.json()["publication_status"] == "hidden"
    assert restored.json()["publication_status"] == "published"
    assert [review.decision for review in await reviews_of(session, product_id)] == [
        ModerationDecision.APPROVED,
        ModerationDecision.HIDDEN,
        ModerationDecision.PUBLISHED,
    ]


async def test_an_unpublished_product_cannot_be_hidden(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    product_id = await a_product_awaiting_review(api_client, session)
    await become_moderator(api_client, session)

    response = await decide(api_client, product_id, "hide")

    assert response.status_code == 409
    assert (await reviews_of(session, product_id)) == []


async def test_an_unapproved_product_cannot_be_published(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    """The rule the machine exists for, seen from the outside."""
    product_id = await a_product_awaiting_review(api_client, session)
    await become_moderator(api_client, session)
    await decide(api_client, product_id, "reject", reason=REASON)

    response = await decide(api_client, product_id, "publish")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "invalid_transition"


async def test_an_unknown_product_is_not_found(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    await become_moderator(api_client, session)

    response = await decide(api_client, str(uuid.uuid4()), "approve")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "product_not_found"


@pytest.mark.parametrize("action", ["approve", "hide", "publish"])
async def test_a_seller_cannot_moderate(
    api_client: AsyncClient, session: AsyncSession, action: str
) -> None:
    product_id = await a_product_awaiting_review(api_client, session)

    response = await decide(api_client, product_id, action)

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
    product_id = await a_product_awaiting_review(api_client, session)
    await become_moderator(api_client, session)

    response = await api_client.post(decision_url(product_id, "approve"))

    assert response.status_code == 403


async def test_a_moderator_has_no_shop_of_their_own(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    await become_moderator(api_client, session)

    assert (await api_client.get(PRODUCTS_URL)).status_code == 403
