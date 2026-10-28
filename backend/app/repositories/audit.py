import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.models import AuditLog


@dataclass(frozen=True)
class JournalFilter:
    """What an administrator narrows the journal by.

    One object for the listing and the count, so the two cannot disagree on what matches —
    the same reason the account filter is one object.
    """

    actor_id: uuid.UUID | None = None
    action: str | None = None
    since: datetime | None = None
    until: datetime | None = None


def _narrow[S: Select[Any]](statement: S, where: JournalFilter) -> S:
    if where.actor_id is not None:
        statement = statement.where(AuditLog.actor_user_id == where.actor_id)
    if where.action is not None:
        # a prefix, so `user.` brings every decision about accounts without listing them
        statement = statement.where(AuditLog.action.startswith(where.action))
    if where.since is not None:
        statement = statement.where(AuditLog.created_at >= where.since)
    if where.until is not None:
        statement = statement.where(AuditLog.created_at <= where.until)
    return statement


async def add(session: AsyncSession, entry: AuditLog) -> AuditLog:
    session.add(entry)
    await session.flush()
    return entry


async def list_entries(
    session: AsyncSession, where: JournalFilter, limit: int, offset: int
) -> Sequence[AuditLog]:
    """Newest first: what happened just now is what an administrator came to look at."""
    result = await session.execute(
        _narrow(select(AuditLog), where)
        .options(joinedload(AuditLog.actor))
        .order_by(AuditLog.created_at.desc(), AuditLog.id)
        .limit(limit)
        .offset(offset)
    )
    return result.unique().scalars().all()


async def count_entries(session: AsyncSession, where: JournalFilter) -> int:
    result = await session.execute(_narrow(select(func.count()).select_from(AuditLog), where))
    return result.scalar_one()
