from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import PasswordResetToken


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
