import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.models import Business, Store


async def get_by_subdomain(session: AsyncSession, subdomain: str) -> Store | None:
    result = await session.execute(select(Store).where(Store.subdomain == subdomain))
    return result.scalar_one_or_none()


async def get_with_business_by_subdomain(session: AsyncSession, subdomain: str) -> Store | None:
    """Business is loaded with the store: the storefront shows its name, description and
    the ways to reach the seller."""
    result = await session.execute(
        select(Store)
        .options(joinedload(Store.business).selectinload(Business.social_links))
        .where(Store.subdomain == subdomain)
    )
    return result.scalar_one_or_none()


async def get_by_business(session: AsyncSession, business_id: uuid.UUID) -> Store | None:
    result = await session.execute(select(Store).where(Store.business_id == business_id))
    return result.scalar_one_or_none()


async def add(session: AsyncSession, store: Store) -> Store:
    session.add(store)
    await session.flush()
    return store
