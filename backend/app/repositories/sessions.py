import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Session


async def add(session: AsyncSession, row: Session) -> Session:
    session.add(row)
    await session.flush()
    return row


async def get_by_hash(session: AsyncSession, token_hash: str) -> Session | None:
    result = await session.execute(select(Session).where(Session.token_hash == token_hash))
    return result.scalar_one_or_none()


async def get_for_user(
    session: AsyncSession, user_id: uuid.UUID, session_id: uuid.UUID
) -> Session | None:
    """Scoped to the owner on purpose: an identifier from somebody else's list must read as
    an identifier that is not there."""
    result = await session.execute(
        select(Session).where(Session.id == session_id, Session.user_id == user_id)
    )
    return result.scalar_one_or_none()


async def revoke(
    session: AsyncSession,
    row: Session,
    reason: str,
    replaced_by_id: uuid.UUID | None = None,
) -> None:
    row.revoked_at = datetime.now(UTC)
    row.revoked_reason = reason
    row.replaced_by_id = replaced_by_id
    await session.flush()


async def revoke_family(session: AsyncSession, family_id: uuid.UUID, reason: str) -> None:
    """One device, however many times its token has been renewed."""
    await session.execute(
        update(Session)
        .where(Session.family_id == family_id, Session.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC), revoked_reason=reason)
    )
    await session.flush()


async def revoke_all_for_user(session: AsyncSession, user_id: uuid.UUID, reason: str) -> None:
    await session.execute(
        update(Session)
        .where(Session.user_id == user_id, Session.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC), revoked_reason=reason)
    )
    await session.flush()


async def revoke_every_other_family(
    session: AsyncSession, user_id: uuid.UUID, keep: uuid.UUID, reason: str
) -> None:
    """ "Sign out everywhere else" — the device asking is the one that stays."""
    await session.execute(
        update(Session)
        .where(
            Session.user_id == user_id,
            Session.family_id != keep,
            Session.revoked_at.is_(None),
        )
        .values(revoked_at=datetime.now(UTC), revoked_reason=reason)
    )
    await session.flush()


async def has_live_family(session: AsyncSession, user_id: uuid.UUID) -> bool:
    """Whether this account is open anywhere at all.

    Asked at sign-in, before the new session exists, so it means "was it already open
    somewhere else" — which is what makes a new device worth writing about. The first sign-in
    on a fresh account is news to nobody, and a letter for every one of somebody's own daily
    logins is a letter they stop reading.
    """
    now = datetime.now(UTC)
    result = await session.execute(
        select(Session.id)
        .where(
            Session.user_id == user_id,
            Session.revoked_at.is_(None),
            Session.idle_expires_at > now,
            Session.absolute_expires_at > now,
        )
        .limit(1)
    )
    return result.scalar_one_or_none() is not None


async def live_for_user(session: AsyncSession, user_id: uuid.UUID) -> Sequence[Session]:
    """The devices somebody is signed in on, newest first.

    One row per family: a family is a device, and the rotations inside it are bookkeeping
    nobody outside this module should have to look at. The newest row carries the current
    times, so it is the one that answers for the family.
    """
    now = datetime.now(UTC)
    result = await session.execute(
        select(Session)
        .where(
            Session.user_id == user_id,
            Session.revoked_at.is_(None),
            Session.idle_expires_at > now,
            Session.absolute_expires_at > now,
        )
        .order_by(Session.last_seen_at.desc())
    )
    rows = result.scalars().all()
    newest_per_family: dict[uuid.UUID, Session] = {}
    for row in rows:
        newest_per_family.setdefault(row.family_id, row)
    return list(newest_per_family.values())
