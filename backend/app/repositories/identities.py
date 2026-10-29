import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import IdentityProvider, UserIdentity


async def add(session: AsyncSession, identity: UserIdentity) -> UserIdentity:
    session.add(identity)
    await session.flush()
    return identity


async def get(
    session: AsyncSession, provider: IdentityProvider, subject: str
) -> UserIdentity | None:
    """By what the provider calls this person — never by the address they happen to show."""
    result = await session.execute(
        select(UserIdentity).where(
            UserIdentity.provider == provider, UserIdentity.provider_subject == subject
        )
    )
    return result.scalar_one_or_none()


async def for_user(session: AsyncSession, user_id: uuid.UUID) -> Sequence[UserIdentity]:
    result = await session.execute(
        select(UserIdentity).where(UserIdentity.user_id == user_id).order_by(UserIdentity.linked_at)
    )
    return result.scalars().all()


async def remove(session: AsyncSession, identity: UserIdentity) -> None:
    await session.delete(identity)
    await session.flush()
