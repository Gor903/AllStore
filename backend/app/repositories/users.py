import uuid
from collections.abc import Sequence
from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Business, User, UserRole, UserStatus
from app.repositories.catalog import LIKE_ESCAPE, like_pattern


def _narrow[S: Select[Any]](
    statement: S, query: str | None, roles: Sequence[UserRole] | None = None
) -> S:
    """Shared by the listing and its count, so the two cannot disagree on what matches."""
    if query:
        statement = statement.where(User.email.ilike(like_pattern(query), escape=LIKE_ESCAPE))
    if roles is not None:
        statement = statement.where(User.role.in_(roles))
    return statement


async def get_by_id(session: AsyncSession, user_id: uuid.UUID) -> User | None:
    return await session.get(User, user_id)


async def get_by_email(session: AsyncSession, email: str) -> User | None:
    result = await session.execute(select(User).where(User.email == email))
    return result.scalar_one_or_none()


async def email_exists(session: AsyncSession, email: str) -> bool:
    result = await session.execute(select(User.id).where(User.email == email))
    return result.scalar_one_or_none() is not None


async def phone_exists(session: AsyncSession, phone: str) -> bool:
    result = await session.execute(select(User.id).where(User.phone == phone))
    return result.scalar_one_or_none() is not None


async def add(session: AsyncSession, user: User) -> User:
    session.add(user)
    await session.flush()
    return user


async def get_business_of(session: AsyncSession, user_id: uuid.UUID) -> Business | None:
    result = await session.execute(select(Business).where(Business.owner_user_id == user_id))
    return result.scalar_one_or_none()


async def get_business_with_reviews(session: AsyncSession, user_id: uuid.UUID) -> Business | None:
    """What the seller's own cabinet shows: the shop and every verdict passed on it, so a
    refusal arrives with the reason attached rather than as a bare status.

    The storefront comes along because a status change moves it too — see
    services/business_moderation._move — and a lazy load there would have nowhere to run.
    """
    result = await session.execute(
        select(Business)
        .options(selectinload(Business.reviews), selectinload(Business.store))
        .where(Business.owner_user_id == user_id)
    )
    return result.scalar_one_or_none()


async def add_business(session: AsyncSession, business: Business) -> Business:
    session.add(business)
    await session.flush()
    return business


async def search(
    session: AsyncSession,
    query: str | None,
    limit: int,
    offset: int,
    roles: Sequence[UserRole] | None = None,
) -> Sequence[User]:
    """Newest first, so an account registered a minute ago is the one on top."""
    result = await session.execute(
        _narrow(select(User), query, roles)
        .order_by(User.created_at.desc(), User.id)
        .limit(limit)
        .offset(offset)
    )
    return result.scalars().all()


async def count_matching(
    session: AsyncSession, query: str | None, roles: Sequence[UserRole] | None = None
) -> int:
    statement = _narrow(select(func.count()).select_from(User), query, roles)
    return (await session.execute(statement)).scalar_one()


async def get_admin(session: AsyncSession) -> User | None:
    """The administrator, whatever their status. There is at most one: a unique partial index
    on `role = 'admin'` is what makes `scalar_one_or_none` safe to say here."""
    result = await session.execute(select(User).where(User.role == UserRole.ADMIN))
    return result.scalar_one_or_none()


async def count_active_admins(session: AsyncSession) -> int:
    result = await session.execute(
        select(func.count())
        .select_from(User)
        .where(User.role == UserRole.ADMIN, User.status == UserStatus.ACTIVE)
    )
    return result.scalar_one()
