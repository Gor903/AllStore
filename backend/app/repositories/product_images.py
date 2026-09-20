import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ProductImage


async def get_owned(
    session: AsyncSession, product_id: uuid.UUID, image_id: uuid.UUID
) -> ProductImage | None:
    """Looked up by product and id together — the product itself is checked against the tenant."""
    result = await session.execute(
        select(ProductImage).where(
            ProductImage.id == image_id, ProductImage.product_id == product_id
        )
    )
    return result.scalar_one_or_none()


async def count_for_product(session: AsyncSession, product_id: uuid.UUID) -> int:
    result = await session.execute(
        select(func.count()).select_from(ProductImage).where(ProductImage.product_id == product_id)
    )
    return result.scalar_one()


async def next_sort_order(session: AsyncSession, product_id: uuid.UUID) -> int:
    """A new photo goes to the end of the gallery, so the cover does not change by itself."""
    result = await session.execute(
        select(func.max(ProductImage.sort_order)).where(ProductImage.product_id == product_id)
    )
    highest = result.scalar_one()
    return 0 if highest is None else highest + 1


async def add(session: AsyncSession, image: ProductImage) -> ProductImage:
    session.add(image)
    await session.flush()
    return image


async def remove(session: AsyncSession, image: ProductImage) -> None:
    await session.delete(image)
    await session.flush()
