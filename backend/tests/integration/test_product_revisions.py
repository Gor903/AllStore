"""A change to a published product waits its turn without taking the product off the shelf.

Before this stage, editing an approved product sent it straight back to `pending` and out of
the catalogue: fixing a typo cost the seller their listing for as long as the queue was busy,
and a refusal of the fix cost them the listing permanently. What is asserted here is that the
buyer goes on seeing the last approved version throughout, and that nothing proposed is ever
thrown away.
"""

import uuid

import pytest
from httpx import AsyncClient, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog, ProductRevision, RevisionStatus
from tests.integration.conftest import (
    PRODUCT_MODERATION,
    PRODUCTS_URL,
    Shop,
    a_live_shop,
    a_product,
    a_published_product,
    anonymous,
    csrf_headers,
    seeded_category,
    switch,
)

pytestmark = pytest.mark.integration

CATALOG_PRODUCTS = "/api/v1/catalog/products"
REASON = "Название обещает то, чего нет на фотографии"
APPROVED_NAME = "Кружка керамическая"
PROPOSED_NAME = "Кружка керамическая ручной работы"


async def edit(client: AsyncClient, product_id: str, **fields: object) -> Response:
    return await client.patch(
        f"{PRODUCTS_URL}/{product_id}", json=fields, headers=csrf_headers(client)
    )


async def decide(client: AsyncClient, product_id: str, action: str, **body: str) -> Response:
    return await client.post(
        f"{PRODUCT_MODERATION}/{product_id}/{action}",
        json=body or None,
        headers=csrf_headers(client),
    )


async def revisions_of(session: AsyncSession, product_id: str) -> list[ProductRevision]:
    result = await session.execute(
        select(ProductRevision)
        .where(ProductRevision.product_id == uuid.UUID(product_id))
        .order_by(ProductRevision.created_at)
    )
    return list(result.scalars().all())


async def catalogue_names(client: AsyncClient) -> list[str]:
    await anonymous(client)
    body = (await client.get(CATALOG_PRODUCTS)).json()
    return [item["name"] for item in body["items"]]


async def a_live_product(
    client: AsyncClient, session: AsyncSession, subdomain: str
) -> tuple[Shop, str]:
    """A shop on the air with one approved product on the shelf."""
    shop = await a_live_shop(client, session, subdomain)
    product_id = await a_published_product(client, session, shop, name=APPROVED_NAME)
    return shop, product_id


async def test_the_buyer_keeps_seeing_the_approved_version_while_a_change_waits(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    shop, product_id = await a_live_product(api_client, session, "keepsshelf")
    switch(api_client, shop.seller)

    await edit(api_client, product_id, name=PROPOSED_NAME)

    assert await catalogue_names(api_client) == [APPROVED_NAME]


async def test_the_change_appears_once_it_is_approved(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    shop, product_id = await a_live_product(api_client, session, "appearslater")
    switch(api_client, shop.seller)
    await edit(api_client, product_id, name=PROPOSED_NAME)

    switch(api_client, shop.moderator)
    approved = await decide(api_client, product_id, "approve")

    assert approved.status_code == 200
    assert await catalogue_names(api_client) == [PROPOSED_NAME]


async def test_a_refused_change_costs_the_seller_nothing_they_had(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    """The listing stays live under the text that was approved before."""
    shop, product_id = await a_live_product(api_client, session, "nothinglost")
    switch(api_client, shop.seller)
    await edit(api_client, product_id, name=PROPOSED_NAME)

    switch(api_client, shop.moderator)
    refused = await decide(api_client, product_id, "reject", reason=REASON)

    assert refused.status_code == 200
    assert refused.json()["moderation_status"] == "approved"
    assert refused.json()["publication_status"] == "published"
    assert await catalogue_names(api_client) == [APPROVED_NAME]


async def test_the_seller_is_told_why_their_change_was_refused(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    shop, product_id = await a_live_product(api_client, session, "toldwhy")
    switch(api_client, shop.seller)
    await edit(api_client, product_id, name=PROPOSED_NAME)
    switch(api_client, shop.moderator)
    await decide(api_client, product_id, "reject", reason=REASON)

    switch(api_client, shop.seller)
    body = (await api_client.get(f"{PRODUCTS_URL}/{product_id}")).json()

    assert body["change_rejection_reason"] == REASON
    # the product itself was never refused, so the other field stays empty
    assert body["rejection_reason"] is None
    assert body["pending_change"] is None


async def test_the_refused_text_is_kept_with_its_reason(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    shop, product_id = await a_live_product(api_client, session, "keepsrefused")
    switch(api_client, shop.seller)
    await edit(api_client, product_id, name=PROPOSED_NAME)
    switch(api_client, shop.moderator)
    await decide(api_client, product_id, "reject", reason=REASON)

    history = await revisions_of(session, product_id)
    assert [item.status for item in history] == [RevisionStatus.APPROVED, RevisionStatus.REJECTED]
    assert history[1].name == PROPOSED_NAME
    assert history[1].reason == REASON


async def test_two_edits_before_a_verdict_make_one_proposal(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    """A second proposal beside the first would leave a moderator guessing which is current,
    and the seller's earlier edit silently unapplied."""
    shop, product_id = await a_live_product(api_client, session, "oneproposal")
    switch(api_client, shop.seller)

    await edit(api_client, product_id, name=PROPOSED_NAME)
    second = await edit(api_client, product_id, description="Новое описание")

    assert second.json()["pending_change"]["name"] == PROPOSED_NAME
    assert second.json()["pending_change"]["description"] == "Новое описание"
    history = await revisions_of(session, product_id)
    waiting = [item for item in history if item.status is RevisionStatus.PENDING]
    assert len(waiting) == 1


async def test_the_edit_it_replaced_is_kept_rather_than_deleted(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    shop, product_id = await a_live_product(api_client, session, "keepssuperseded")
    switch(api_client, shop.seller)
    await edit(api_client, product_id, name=PROPOSED_NAME)
    await edit(api_client, product_id, name="Третье название")

    history = await revisions_of(session, product_id)
    assert [item.status for item in history] == [
        RevisionStatus.APPROVED,
        RevisionStatus.SUPERSEDED,
        RevisionStatus.PENDING,
    ]
    assert history[1].name == PROPOSED_NAME


async def test_a_waiting_change_puts_the_product_in_the_queue(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    shop, product_id = await a_live_product(api_client, session, "backinqueue")
    switch(api_client, shop.moderator)
    assert (await api_client.get(PRODUCT_MODERATION)).json()["total"] == 0

    switch(api_client, shop.seller)
    await edit(api_client, product_id, name=PROPOSED_NAME)

    switch(api_client, shop.moderator)
    queue = (await api_client.get(PRODUCT_MODERATION)).json()
    assert queue["total"] == 1
    assert queue["items"][0]["id"] == product_id


async def test_the_queue_shows_the_moderator_both_versions(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    """Judging a change means comparing it with what is on the shelf, so both travel."""
    shop, product_id = await a_live_product(api_client, session, "bothversions")
    switch(api_client, shop.seller)
    await edit(api_client, product_id, name=PROPOSED_NAME)

    switch(api_client, shop.moderator)
    item = (await api_client.get(PRODUCT_MODERATION)).json()["items"][0]

    assert item["name"] == APPROVED_NAME
    assert item["proposed"]["name"] == PROPOSED_NAME
    assert item["proposed"]["category_name"]
    assert item["is_change"] is True


async def test_a_brand_new_product_is_not_marked_as_a_change(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    shop = await a_live_shop(api_client, session, "firsttime")
    await a_product(api_client, session, shop, name="Новый товар")

    switch(api_client, shop.moderator)
    item = (await api_client.get(PRODUCT_MODERATION)).json()["items"][0]

    assert item["is_change"] is False
    assert item["proposed"]["name"] == "Новый товар"


async def test_changing_the_price_does_not_queue_anything(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    """A moderator did not approve the price, and holding it hostage to a queue would make
    the shelf wrong rather than careful."""
    shop, product_id = await a_live_product(api_client, session, "pricefree")
    switch(api_client, shop.seller)

    response = await edit(api_client, product_id, price="1600.00", stock_quantity=3)

    assert response.json()["price"] == "1600.00"
    assert response.json()["pending_change"] is None
    switch(api_client, shop.moderator)
    assert (await api_client.get(PRODUCT_MODERATION)).json()["total"] == 0


async def test_approving_a_change_does_not_undo_a_hide(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    shop, product_id = await a_live_product(api_client, session, "stayshidden")
    switch(api_client, shop.moderator)
    await decide(api_client, product_id, "hide")
    switch(api_client, shop.seller)
    await edit(api_client, product_id, name=PROPOSED_NAME)

    switch(api_client, shop.moderator)
    approved = await decide(api_client, product_id, "approve")

    assert approved.json()["publication_status"] == "hidden"
    assert approved.json()["name"] == PROPOSED_NAME
    assert await catalogue_names(api_client) == []


async def test_there_is_nothing_to_approve_without_a_proposal(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    shop, product_id = await a_live_product(api_client, session, "nothingwaiting")
    switch(api_client, shop.moderator)

    response = await decide(api_client, product_id, "approve")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "invalid_transition"


async def test_asking_again_without_changing_anything_is_allowed_once(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    """For everything moderation looks at that is not a moderated field — the photographs."""
    shop, product_id = await a_live_product(api_client, session, "asksagain")
    switch(api_client, shop.seller)

    first = await api_client.post(
        f"{PRODUCTS_URL}/{product_id}/submit", headers=csrf_headers(api_client)
    )
    second = await api_client.post(
        f"{PRODUCTS_URL}/{product_id}/submit", headers=csrf_headers(api_client)
    )

    assert first.status_code == 200
    assert second.status_code == 409


async def test_archiving_takes_the_waiting_change_out_of_the_queue(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    """A proposal for something nobody sells any more is not a thing to judge."""
    shop, product_id = await a_live_product(api_client, session, "archived")
    switch(api_client, shop.seller)
    await edit(api_client, product_id, name=PROPOSED_NAME)
    await api_client.delete(f"{PRODUCTS_URL}/{product_id}", headers=csrf_headers(api_client))

    switch(api_client, shop.moderator)
    assert (await api_client.get(PRODUCT_MODERATION)).json()["total"] == 0
    history = await revisions_of(session, product_id)
    assert history[-1].status is RevisionStatus.SUPERSEDED


async def test_the_queue_serves_whoever_has_waited_longest_for_a_verdict(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    """By the age of the proposal, not of the product: an old shop editing a description
    today must not jump ahead of a newcomer who filed yesterday."""
    old_shop, old_product = await a_live_product(api_client, session, "oldshop")
    new_shop = await a_live_shop(api_client, session, "newshop")
    new_product = await a_product(api_client, session, new_shop, name="Товар новичка")
    switch(api_client, old_shop.seller)
    await edit(api_client, old_product, name=PROPOSED_NAME)

    switch(api_client, old_shop.moderator)
    queue = (await api_client.get(PRODUCT_MODERATION)).json()

    assert [item["id"] for item in queue["items"]] == [new_product, old_product]


async def test_a_seller_never_judges_their_own_proposal(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    shop, product_id = await a_live_product(api_client, session, "notjudge")
    switch(api_client, shop.seller)
    await edit(api_client, product_id, name=PROPOSED_NAME)

    response = await decide(api_client, product_id, "approve")

    assert response.status_code == 403


async def test_every_verdict_on_a_product_reaches_the_journal(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    shop, product_id = await a_live_product(api_client, session, "journalled")
    switch(api_client, shop.seller)
    await edit(api_client, product_id, name=PROPOSED_NAME)
    switch(api_client, shop.moderator)
    await decide(api_client, product_id, "reject", reason=REASON)
    await decide(api_client, product_id, "hide")
    await decide(api_client, product_id, "publish")

    written = (
        (await session.execute(select(AuditLog).order_by(AuditLog.created_at))).scalars().all()
    )
    assert [entry.action for entry in written] == [
        "business.approved",
        "product.approved",
        "product.rejected",
        "product.hidden",
        "product.published",
    ]


async def test_a_verdict_names_the_proposal_it_was_about(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    from app.models import ModerationReview

    shop, product_id = await a_live_product(api_client, session, "namesproposal")
    switch(api_client, shop.seller)
    await edit(api_client, product_id, name=PROPOSED_NAME)
    switch(api_client, shop.moderator)
    await decide(api_client, product_id, "reject", reason=REASON)

    verdicts = (
        (
            await session.execute(
                select(ModerationReview)
                .where(ModerationReview.product_id == uuid.UUID(product_id))
                .order_by(ModerationReview.created_at)
            )
        )
        .scalars()
        .all()
    )
    history = await revisions_of(session, product_id)
    assert verdicts[-1].revision_id == history[-1].id


async def test_a_category_change_waits_like_any_other(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    shop, product_id = await a_live_product(api_client, session, "categorywaits")
    other = await seeded_category(session, "books")
    switch(api_client, shop.seller)

    response = await edit(api_client, product_id, category_id=str(other.id))

    assert response.json()["category_id"] != str(other.id)
    assert response.json()["pending_change"]["category_id"] == str(other.id)
