import uuid
from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.models import Category, Product, Store
from app.repositories import catalog
from app.services.products import ProductNotFoundError


class UnknownCategoryError(NotFoundError):
    code = "category_not_found"


async def list_products(
    session: AsyncSession,
    *,
    query: str | None,
    category_slug: str | None,
    subdomain: str | None,
    limit: int,
    offset: int,
) -> tuple[Sequence[Product], int]:
    category_ids = None if category_slug is None else await _with_children(session, category_slug)
    return (
        await catalog.list_products(
            session,
            query=query,
            category_ids=category_ids,
            subdomain=subdomain,
            limit=limit,
            offset=offset,
        ),
        await catalog.count_products(
            session, query=query, category_ids=category_ids, subdomain=subdomain
        ),
    )


async def get_product(session: AsyncSession, product_id: uuid.UUID) -> Product:
    """A product that is not public answers exactly as one that does not exist."""
    product = await catalog.get_product(session, product_id)
    if product is None:
        raise ProductNotFoundError("Товар не найден")
    return product


async def list_stores(
    session: AsyncSession, limit: int, offset: int
) -> tuple[Sequence[Store], int]:
    return (
        await catalog.list_stores(session, limit, offset),
        await catalog.count_stores(session),
    )


async def list_categories(session: AsyncSession) -> Sequence[Category]:
    return await catalog.list_categories(session)


async def _with_children(session: AsyncSession, slug: str) -> list[uuid.UUID]:
    """A top-level category stands for everything filed under it — that is what a shopper means."""
    category = await catalog.get_category_by_slug(session, slug)
    if category is None:
        raise UnknownCategoryError("Категория не найдена")
    return [category.id, *await catalog.list_child_ids(session, category.id)]
