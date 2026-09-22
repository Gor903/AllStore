import uuid
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Category, CategoryStatus


async def get_active_by_id(session: AsyncSession, category_id: uuid.UUID) -> Category | None:
    """Hidden categories are not offered, so a product cannot be filed under one."""
    result = await session.execute(
        select(Category).where(Category.id == category_id, Category.status == CategoryStatus.ACTIVE)
    )
    return result.scalar_one_or_none()


async def get_by_id(session: AsyncSession, category_id: uuid.UUID) -> Category | None:
    return await session.get(Category, category_id)


async def get_by_slug(session: AsyncSession, slug: str) -> Category | None:
    result = await session.execute(select(Category).where(Category.slug == slug))
    return result.scalar_one_or_none()


async def list_tree(session: AsyncSession) -> Sequence[Category]:
    """The whole tree, hidden branches included: an administrator manages what a visitor
    must not see just as much as what they may."""
    result = await session.execute(
        select(Category)
        .options(selectinload(Category.children))
        .where(Category.parent_id.is_(None))
        .order_by(Category.name)
    )
    return result.unique().scalars().all()


async def count_children(session: AsyncSession, category_id: uuid.UUID) -> int:
    result = await session.execute(
        select(func.count()).select_from(Category).where(Category.parent_id == category_id)
    )
    return result.scalar_one()


async def add(session: AsyncSession, category: Category) -> Category:
    session.add(category)
    await session.flush()
    return category
