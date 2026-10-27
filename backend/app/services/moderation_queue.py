"""The moderator's side of a product: what is waiting, and what a verdict does to it.

The queue holds proposals, not products. A product that is already on the shelf and has
nothing proposed is not waiting for anybody, and the same product with a change pending is —
so the thing that queues is the revision, and the product comes along as its context.
"""

import uuid
from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ModerationDecision, ModerationReview, Product, ProductRevision, User
from app.repositories import moderation as moderation_repo
from app.services import audit, moderation
from app.services.products import ProductNotFoundError

ENTITY = "product"


async def list_queue(
    session: AsyncSession, limit: int, offset: int
) -> tuple[Sequence[Product], int]:
    return (
        await moderation_repo.list_queue(session, limit, offset),
        await moderation_repo.count_queue(session),
    )


async def search(
    session: AsyncSession, query: str, limit: int, offset: int
) -> tuple[Sequence[Product], int]:
    """Finding a product that is not in the queue — the one a complaint is about."""
    return (
        await moderation_repo.search(session, query, limit, offset),
        await moderation_repo.count_search(session, query),
    )


async def approve(session: AsyncSession, moderator: User, product_id: uuid.UUID) -> Product:
    product = await _under_review(session, product_id)
    revision = _proposal_of(product)
    moderation.approve_revision(product, revision)
    await _record(session, product, moderator, ModerationDecision.APPROVED, None, revision)
    await audit.record(session, moderator, "product.approved", ENTITY, product.id)
    return product


async def reject(
    session: AsyncSession, moderator: User, product_id: uuid.UUID, reason: str
) -> Product:
    product = await _under_review(session, product_id)
    revision = _proposal_of(product)
    moderation.reject_revision(product, revision, reason)
    await _record(session, product, moderator, ModerationDecision.REJECTED, reason, revision)
    await audit.record(session, moderator, "product.rejected", ENTITY, product.id, reason=reason)
    return product


async def hide(session: AsyncSession, moderator: User, product_id: uuid.UUID) -> Product:
    """About the product rather than about a proposal: what comes off the shelf is the
    version the buyer is looking at."""
    product = await _under_review(session, product_id)
    moderation.hide(product)
    await _record(session, product, moderator, ModerationDecision.HIDDEN, None, None)
    await audit.record(session, moderator, "product.hidden", ENTITY, product.id)
    return product


async def publish(session: AsyncSession, moderator: User, product_id: uuid.UUID) -> Product:
    """Takes back a hide. The approval behind the product is the one it already had."""
    product = await _under_review(session, product_id)
    moderation.publish(product)
    await _record(session, product, moderator, ModerationDecision.PUBLISHED, None, None)
    await audit.record(session, moderator, "product.published", ENTITY, product.id)
    return product


def _proposal_of(product: Product) -> ProductRevision:
    revision = product.pending_revision
    if revision is None:
        raise moderation.InvalidTransitionError("У этого товара нет изменений на проверке")
    return revision


async def _under_review(session: AsyncSession, product_id: uuid.UUID) -> Product:
    product = await moderation_repo.get_for_review(session, product_id)
    if product is None:
        raise ProductNotFoundError("Товар не найден")
    return product


async def _record(
    session: AsyncSession,
    product: Product,
    moderator: User,
    decision: ModerationDecision,
    reason: str | None,
    revision: ProductRevision | None,
) -> None:
    await moderation_repo.add_review(
        session,
        ModerationReview(
            product_id=product.id,
            revision_id=None if revision is None else revision.id,
            moderator_id=moderator.id,
            decision=decision,
            reason=reason,
        ),
    )
    # the verdict just written is part of what the answer carries, and updated_at was
    # recomputed by the database when the product row changed
    await session.refresh(product, attribute_names=["reviews", "revisions", "updated_at"])
