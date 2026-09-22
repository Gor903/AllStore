import uuid
from collections.abc import Sequence

from sqlalchemy import ColumnElement, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import contains_eager, selectinload

from app.models import Business, ModerationReview, ModerationStatus, Product
from app.repositories.catalog import LIKE_ESCAPE, like_pattern

# The queries here deliberately do not filter by business_id: a moderator works across every
# tenant, and that is the one role for which the isolation rule does not hold. Archived
# products are left out — a seller has already taken them off the shelf themselves.


async def get_for_review(session: AsyncSession, product_id: uuid.UUID) -> Product | None:
    result = await session.execute(
        select(Product)
        # the category, the seller and the storefront come with it: a moderator judges a
        # product, and a pair of identifiers is not something anyone can judge
        .options(
            selectinload(Product.images),
            selectinload(Product.reviews),
            selectinload(Product.category),
            selectinload(Product.business).selectinload(Business.store),
        )
        .where(Product.id == product_id, Product.archived_at.is_(None))
    )
    return result.scalar_one_or_none()


async def list_queue(session: AsyncSession, limit: int, offset: int) -> Sequence[Product]:
    """Oldest first: whoever has waited longest is looked at first."""
    result = await session.execute(
        select(Product)
        # the category, the seller and the storefront come with it: a moderator judges a
        # product, and a pair of identifiers is not something anyone can judge
        .options(
            selectinload(Product.images),
            selectinload(Product.reviews),
            selectinload(Product.category),
            selectinload(Product.business).selectinload(Business.store),
        )
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


def _found(query: str) -> ColumnElement[bool]:
    """By product name or by shop: a moderator acting on a complaint usually knows one
    or the other, rarely an identifier."""
    pattern = like_pattern(query)
    return or_(
        Product.name.ilike(pattern, escape=LIKE_ESCAPE),
        Business.display_name.ilike(pattern, escape=LIKE_ESCAPE),
    )


async def search(session: AsyncSession, query: str, limit: int, offset: int) -> Sequence[Product]:
    """Every status, not just the queue: what a moderator is sent after is usually already
    on the shelf. Archived is left out — the seller has withdrawn it themselves."""
    result = await session.execute(
        select(Product)
        .join(Product.business)
        .options(
            contains_eager(Product.business).selectinload(Business.store),
            selectinload(Product.images),
            selectinload(Product.reviews),
            selectinload(Product.category),
        )
        .where(Product.archived_at.is_(None), _found(query))
        .order_by(Product.created_at.desc(), Product.id)
        .limit(limit)
        .offset(offset)
    )
    return result.unique().scalars().all()


async def count_search(session: AsyncSession, query: str) -> int:
    result = await session.execute(
        select(func.count())
        .select_from(Product)
        .join(Product.business)
        .where(Product.archived_at.is_(None), _found(query))
    )
    return result.scalar_one()
