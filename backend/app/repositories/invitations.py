import uuid
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import ModeratorInvitation


async def add(session: AsyncSession, invitation: ModeratorInvitation) -> ModeratorInvitation:
    session.add(invitation)
    await session.flush()
    return invitation


async def get(session: AsyncSession, invitation_id: uuid.UUID) -> ModeratorInvitation | None:
    return await session.get(ModeratorInvitation, invitation_id)


async def get_live_for(session: AsyncSession, email: str) -> ModeratorInvitation | None:
    """The invitation that is open right now for this address, expired or not. At most one
    exists: a unique partial index on `used_at IS NULL AND revoked_at IS NULL` says so."""
    result = await session.execute(
        select(ModeratorInvitation).where(
            ModeratorInvitation.email == email,
            ModeratorInvitation.used_at.is_(None),
            ModeratorInvitation.revoked_at.is_(None),
        )
    )
    return result.scalar_one_or_none()


async def claim(
    session: AsyncSession, token_hash: str, now: datetime
) -> ModeratorInvitation | None:
    """Spends the invitation, or answers that there was nothing to spend.

    One statement, because this is the race the whole table exists to lose gracefully: two
    requests arriving with the same link both pass any check made beforehand, and only the
    UPDATE can decide between them. The row is locked by the first, re-read by the second
    after the first commits, and by then `used_at` no longer matches.
    """
    result = await session.execute(
        update(ModeratorInvitation)
        .where(
            ModeratorInvitation.token_hash == token_hash,
            ModeratorInvitation.used_at.is_(None),
            ModeratorInvitation.revoked_at.is_(None),
            ModeratorInvitation.expires_at > now,
        )
        .values(used_at=now)
        .returning(ModeratorInvitation)
    )
    return result.scalars().one_or_none()


async def list_all(
    session: AsyncSession, limit: int, offset: int
) -> tuple[Sequence[ModeratorInvitation], int]:
    rows = await session.execute(
        select(ModeratorInvitation)
        .options(
            selectinload(ModeratorInvitation.created_by),
            selectinload(ModeratorInvitation.accepted_user),
            selectinload(ModeratorInvitation.revoked_by),
        )
        .order_by(ModeratorInvitation.created_at.desc(), ModeratorInvitation.id)
        .limit(limit)
        .offset(offset)
    )
    total = await session.execute(select(func.count()).select_from(ModeratorInvitation))
    return rows.scalars().all(), total.scalar_one()
