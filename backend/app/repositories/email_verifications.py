import uuid
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import EmailVerification


async def add(session: AsyncSession, row: EmailVerification) -> EmailVerification:
    session.add(row)
    await session.flush()
    return row


async def get_by_hash(session: AsyncSession, token_hash: str) -> EmailVerification | None:
    result = await session.execute(
        select(EmailVerification).where(EmailVerification.token_hash == token_hash)
    )
    return result.scalar_one_or_none()


async def live_for_user(session: AsyncSession, user_id: uuid.UUID) -> EmailVerification | None:
    """The request this account is currently waiting on, if any.

    What makes a pending address expressible without a column to hold it: an account is
    waiting to move when this row names an address other than its own.
    """
    now = datetime.now(UTC)
    result = await session.execute(
        select(EmailVerification)
        .where(
            EmailVerification.user_id == user_id,
            EmailVerification.used_at.is_(None),
            EmailVerification.expires_at > now,
        )
        .order_by(EmailVerification.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def spend(session: AsyncSession, row: EmailVerification) -> None:
    row.used_at = datetime.now(UTC)
    await session.flush()


async def supersede_all(session: AsyncSession, user_id: uuid.UUID) -> None:
    """Asking again puts every earlier link out of use.

    Without this, a letter dug out of an old inbox could undo a later decision — somebody who
    asked to move to a second address would still be one click away from the first.
    """
    await session.execute(
        update(EmailVerification)
        .where(EmailVerification.user_id == user_id, EmailVerification.used_at.is_(None))
        .values(used_at=datetime.now(UTC))
    )
    await session.flush()
