import uuid
from collections.abc import Sequence

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import SocialLink


async def list_for_business(session: AsyncSession, business_id: uuid.UUID) -> Sequence[SocialLink]:
    result = await session.execute(
        select(SocialLink)
        .where(SocialLink.business_id == business_id)
        .order_by(SocialLink.platform)
    )
    return result.scalars().all()


async def count_for_business(session: AsyncSession, business_id: uuid.UUID) -> int:
    result = await session.execute(
        select(func.count()).select_from(SocialLink).where(SocialLink.business_id == business_id)
    )
    return result.scalar_one()


async def replace(
    session: AsyncSession, business_id: uuid.UUID, links: list[SocialLink]
) -> Sequence[SocialLink]:
    """The DELETE runs before the INSERTs, so a platform kept in place does not collide
    with its own row on the unique index."""
    await session.execute(delete(SocialLink).where(SocialLink.business_id == business_id))
    session.add_all(links)
    await session.flush()
    return await list_for_business(session, business_id)
