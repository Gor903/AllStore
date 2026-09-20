import uuid
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Product


async def get_owned(
    session: AsyncSession, business_id: uuid.UUID, product_id: uuid.UUID
) -> Product | None:
    """A product is looked up by owner and id together — never by id alone."""
    result = await session.execute(
        select(Product)
        .options(selectinload(Product.images))
        .where(
            Product.id == product_id,
            Product.business_id == business_id,
            Product.archived_at.is_(None),
        )
    )
    return result.scalar_one_or_none()


async def list_for_business(
    session: AsyncSession, business_id: uuid.UUID, limit: int, offset: int
) -> Sequence[Product]:
    # id breaks the tie: two products created in the same millisecond must not swap pages
    result = await session.execute(
        select(Product)
        .options(selectinload(Product.images))
        .where(Product.business_id == business_id, Product.archived_at.is_(None))
        .order_by(Product.created_at.desc(), Product.id)
        .limit(limit)
        .offset(offset)
    )
    return result.scalars().all()


async def count_for_business(session: AsyncSession, business_id: uuid.UUID) -> int:
    result = await session.execute(
        select(func.count())
        .select_from(Product)
        .where(Product.business_id == business_id, Product.archived_at.is_(None))
    )
    return result.scalar_one()


async def add(session: AsyncSession, product: Product) -> Product:
    session.add(product)
    await session.flush()
    return product
