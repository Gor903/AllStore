import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Store


async def get_by_subdomain(session: AsyncSession, subdomain: str) -> Store | None:
    result = await session.execute(select(Store).where(Store.subdomain == subdomain))
    return result.scalar_one_or_none()


async def get_by_business(session: AsyncSession, business_id: uuid.UUID) -> Store | None:
    result = await session.execute(select(Store).where(Store.business_id == business_id))
    return result.scalar_one_or_none()


async def add(session: AsyncSession, store: Store) -> Store:
    session.add(store)
    await session.flush()
    return store
