import uuid
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import AccountBlock


async def add(session: AsyncSession, block: AccountBlock) -> AccountBlock:
    session.add(block)
    await session.flush()
    return block


async def get_in_force(session: AsyncSession, user_id: uuid.UUID) -> AccountBlock | None:
    """The ban that is on right now, if any. At most one exists: a unique partial index on
    `revoked_at IS NULL` is what makes that a fact rather than a hope."""
    result = await session.execute(
        select(AccountBlock).where(
            AccountBlock.user_id == user_id, AccountBlock.revoked_at.is_(None)
        )
    )
    return result.scalar_one_or_none()


async def history(
    session: AsyncSession, user_id: uuid.UUID, limit: int, offset: int
) -> tuple[Sequence[AccountBlock], int]:
    """Newest first — what matters most is the decision in force, or the last one taken."""
    rows = await session.execute(
        select(AccountBlock)
        .options(selectinload(AccountBlock.actor), selectinload(AccountBlock.revoked_by))
        .where(AccountBlock.user_id == user_id)
        .order_by(AccountBlock.created_at.desc(), AccountBlock.id)
        .limit(limit)
        .offset(offset)
    )
    total = await session.execute(
        select(func.count()).select_from(AccountBlock).where(AccountBlock.user_id == user_id)
    )
    return rows.scalars().all(), total.scalar_one()
