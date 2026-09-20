import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Category, CategoryStatus


async def get_active_by_id(session: AsyncSession, category_id: uuid.UUID) -> Category | None:
    """Hidden categories are not offered, so a product cannot be filed under one."""
    result = await session.execute(
        select(Category).where(Category.id == category_id, Category.status == CategoryStatus.ACTIVE)
    )
    return result.scalar_one_or_none()
