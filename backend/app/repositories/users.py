import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Business, User


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


async def add_business(session: AsyncSession, business: Business) -> Business:
    session.add(business)
    await session.flush()
    return business
