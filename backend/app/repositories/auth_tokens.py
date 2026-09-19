import uuid
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import PasswordResetToken, RefreshToken


async def add_refresh_token(session: AsyncSession, token: RefreshToken) -> RefreshToken:
    session.add(token)
    await session.flush()
    return token


async def get_refresh_token(session: AsyncSession, token_hash: str) -> RefreshToken | None:
    result = await session.execute(
        select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    )
    return result.scalar_one_or_none()


async def revoke_refresh_token(
    session: AsyncSession, token: RefreshToken, replaced_by_id: uuid.UUID | None = None
) -> None:
    token.revoked_at = datetime.now(UTC)
    token.replaced_by_id = replaced_by_id
    await session.flush()


async def revoke_all_for_user(session: AsyncSession, user_id: uuid.UUID) -> None:
    """Used when a revoked token is presented again: the whole family is treated as stolen."""
    await session.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC))
    )
    await session.flush()


async def add_password_reset_token(
    session: AsyncSession, token: PasswordResetToken
) -> PasswordResetToken:
    session.add(token)
    await session.flush()
    return token


async def get_password_reset_token(
    session: AsyncSession, token_hash: str
) -> PasswordResetToken | None:
    result = await session.execute(
        select(PasswordResetToken).where(PasswordResetToken.token_hash == token_hash)
    )
    return result.scalar_one_or_none()


async def mark_password_reset_used(session: AsyncSession, token: PasswordResetToken) -> None:
    token.used_at = datetime.now(UTC)
    await session.flush()
