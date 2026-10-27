import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import ProductRevision, RevisionStatus


async def add(session: AsyncSession, revision: ProductRevision) -> ProductRevision:
    session.add(revision)
    await session.flush()
    return revision


async def get_pending(session: AsyncSession, product_id: uuid.UUID) -> ProductRevision | None:
    """At most one exists: a unique partial index on `status = 'pending'` says so, which is
    what lets a moderator act on a product without being asked which proposal they mean."""
    result = await session.execute(
        select(ProductRevision)
        .options(selectinload(ProductRevision.category))
        .where(
            ProductRevision.product_id == product_id,
            ProductRevision.status == RevisionStatus.PENDING,
        )
    )
    return result.scalar_one_or_none()
