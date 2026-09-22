from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.models import AuditLog


async def add(session: AsyncSession, entry: AuditLog) -> AuditLog:
    session.add(entry)
    await session.flush()
    return entry


async def list_entries(session: AsyncSession, limit: int, offset: int) -> Sequence[AuditLog]:
    """Newest first: what happened just now is what an administrator came to look at."""
    result = await session.execute(
        select(AuditLog)
        .options(joinedload(AuditLog.actor))
        .order_by(AuditLog.created_at.desc(), AuditLog.id)
        .limit(limit)
        .offset(offset)
    )
    return result.unique().scalars().all()


async def count_entries(session: AsyncSession) -> int:
    result = await session.execute(select(func.count()).select_from(AuditLog))
    return result.scalar_one()
