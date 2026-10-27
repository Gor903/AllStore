import uuid
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Business, BusinessModerationReview, BusinessStatus

# Like the product queue, these queries look across every tenant: a moderator is the one
# role the isolation rule does not bind.


async def get_with_store(session: AsyncSession, business_id: uuid.UUID) -> Business | None:
    result = await session.execute(
        select(Business)
        .options(selectinload(Business.store), selectinload(Business.reviews))
        .where(Business.id == business_id)
    )
    return result.scalar_one_or_none()


async def list_pending(session: AsyncSession, limit: int, offset: int) -> Sequence[Business]:
    """Oldest first: whoever registered earliest waits least."""
    result = await session.execute(
        select(Business)
        # the history comes along: an applicant who was refused once and answered it is not
        # the same case as one nobody has looked at yet
        .options(selectinload(Business.store), selectinload(Business.reviews))
        .where(Business.status == BusinessStatus.PENDING)
        .order_by(Business.created_at, Business.id)
        .limit(limit)
        .offset(offset)
    )
    return result.scalars().all()


async def count_pending(session: AsyncSession) -> int:
    result = await session.execute(
        select(func.count()).select_from(Business).where(Business.status == BusinessStatus.PENDING)
    )
    return result.scalar_one()


async def add_review(
    session: AsyncSession, review: BusinessModerationReview
) -> BusinessModerationReview:
    session.add(review)
    await session.flush()
    return review
