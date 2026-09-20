import uuid
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import ModerationReview, ModerationStatus, Product

# The queries here deliberately do not filter by business_id: a moderator works across every
# tenant, and that is the one role for which the isolation rule does not hold. Archived
# products are left out — a seller has already taken them off the shelf themselves.


async def get_for_review(session: AsyncSession, product_id: uuid.UUID) -> Product | None:
    result = await session.execute(
        select(Product)
        .options(selectinload(Product.images), selectinload(Product.reviews))
        .where(Product.id == product_id, Product.archived_at.is_(None))
    )
    return result.scalar_one_or_none()


async def list_queue(session: AsyncSession, limit: int, offset: int) -> Sequence[Product]:
    """Oldest first: whoever has waited longest is looked at first."""
    result = await session.execute(
        select(Product)
        .options(selectinload(Product.images), selectinload(Product.reviews))
        .where(
            Product.moderation_status == ModerationStatus.PENDING,
            Product.archived_at.is_(None),
        )
        .order_by(Product.created_at, Product.id)
        .limit(limit)
        .offset(offset)
    )
    return result.scalars().all()


async def count_queue(session: AsyncSession) -> int:
    result = await session.execute(
        select(func.count())
        .select_from(Product)
        .where(
            Product.moderation_status == ModerationStatus.PENDING,
            Product.archived_at.is_(None),
        )
    )
    return result.scalar_one()


async def add_review(session: AsyncSession, review: ModerationReview) -> ModerationReview:
    session.add(review)
    await session.flush()
    return review
