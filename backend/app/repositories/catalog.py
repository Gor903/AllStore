import uuid
from collections.abc import Sequence
from typing import Any

from sqlalchemy import Select, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import contains_eager, selectinload

from app.models import (
    Business,
    BusinessStatus,
    Category,
    CategoryStatus,
    ModerationStatus,
    Product,
    PublicationStatus,
    Store,
    StoreStatus,
)

LIKE_ESCAPE = "\\"

# What a visitor may see, in one place. Every public query starts here, so a product cannot
# reach the catalogue through a query that forgot one of these.
PUBLIC_PRODUCT = (
    Product.publication_status == PublicationStatus.PUBLISHED,
    # published already implies it, but a query is not the place to rely on that
    Product.moderation_status == ModerationStatus.APPROVED,
    Product.archived_at.is_(None),
    Business.status == BusinessStatus.ACTIVE,
    Store.status == StoreStatus.ACTIVE,
)


def like_pattern(query: str) -> str:
    """% and _ are wildcards, so a query containing them must not widen the search."""
    escaped = (
        query.replace(LIKE_ESCAPE, LIKE_ESCAPE * 2)
        .replace("%", f"{LIKE_ESCAPE}%")
        .replace("_", f"{LIKE_ESCAPE}_")
    )
    return f"%{escaped}%"


def _public_products() -> Select[tuple[Product]]:
    return select(Product).join(Product.business).join(Business.store).where(*PUBLIC_PRODUCT)


def _narrow[S: Select[Any]](
    statement: S,
    query: str | None,
    category_ids: Sequence[uuid.UUID] | None,
    subdomain: str | None,
) -> S:
    """Shared by the listing and its count, so the two can never disagree on what matches."""
    if query:
        pattern = like_pattern(query)
        statement = statement.where(
            or_(
                Product.name.ilike(pattern, escape=LIKE_ESCAPE),
                Product.description.ilike(pattern, escape=LIKE_ESCAPE),
            )
        )
    if category_ids is not None:
        statement = statement.where(Product.category_id.in_(category_ids))
    if subdomain is not None:
        statement = statement.where(Store.subdomain == subdomain)
    return statement


async def list_products(
    session: AsyncSession,
    *,
    query: str | None,
    category_ids: Sequence[uuid.UUID] | None,
    subdomain: str | None,
    limit: int,
    offset: int,
) -> Sequence[Product]:
    statement = _narrow(_public_products(), query, category_ids, subdomain)
    result = await session.execute(
        statement.options(
            contains_eager(Product.business).contains_eager(Business.store),
            selectinload(Product.images),
            selectinload(Product.category),
        )
        # newest first, id breaks the tie so two products of one moment keep their pages
        .order_by(Product.created_at.desc(), Product.id)
        .limit(limit)
        .offset(offset)
    )
    return result.unique().scalars().all()


async def list_matching_ids(
    session: AsyncSession,
    *,
    query: str | None,
    category_ids: Sequence[uuid.UUID] | None,
    subdomain: str | None,
    limit: int,
) -> list[uuid.UUID]:
    """Identifiers of the exact matches, newest first — the same set the listing shows.

    Used when the ordering has to be merged with another one; loading whole products only to
    throw most of them away would be the alternative.
    """
    statement = _narrow(
        select(Product.id).join(Product.business).join(Business.store).where(*PUBLIC_PRODUCT),
        query,
        category_ids,
        subdomain,
    )
    result = await session.execute(
        statement.order_by(Product.created_at.desc(), Product.id).limit(limit)
    )
    return list(result.scalars().all())


async def keep_public(
    session: AsyncSession,
    ids: Sequence[uuid.UUID],
    *,
    category_ids: Sequence[uuid.UUID] | None,
    subdomain: str | None,
) -> set[uuid.UUID]:
    """Which of these products a visitor may actually see.

    The search index knows nothing about moderation, publication or a shop being off the air —
    and must not. This is where identifiers from anywhere meet the one rule that decides
    visibility, the same `PUBLIC_PRODUCT` the listing itself is built on.
    """
    if not ids:
        return set()
    statement = _narrow(
        select(Product.id)
        .join(Product.business)
        .join(Business.store)
        .where(*PUBLIC_PRODUCT, Product.id.in_(ids)),
        None,
        category_ids,
        subdomain,
    )
    return set((await session.execute(statement)).scalars().all())


async def list_products_by_ids(
    session: AsyncSession, ids: Sequence[uuid.UUID]
) -> Sequence[Product]:
    """The products behind an already-decided order; the caller restores that order."""
    if not ids:
        return []
    result = await session.execute(
        _public_products()
        .options(
            contains_eager(Product.business).contains_eager(Business.store),
            selectinload(Product.images),
            selectinload(Product.category),
        )
        .where(Product.id.in_(ids))
    )
    return result.unique().scalars().all()


async def count_products(
    session: AsyncSession,
    *,
    query: str | None,
    category_ids: Sequence[uuid.UUID] | None,
    subdomain: str | None,
) -> int:
    statement = _narrow(
        select(func.count())
        .select_from(Product)
        .join(Product.business)
        .join(Business.store)
        .where(*PUBLIC_PRODUCT),
        query,
        category_ids,
        subdomain,
    )
    return (await session.execute(statement)).scalar_one()


async def get_product(session: AsyncSession, product_id: uuid.UUID) -> Product | None:
    result = await session.execute(
        _public_products()
        .options(
            contains_eager(Product.business).contains_eager(Business.store),
            # the card shows how to reach the seller, and a lazy load has nowhere to run here
            contains_eager(Product.business).selectinload(Business.social_links),
            selectinload(Product.images),
            selectinload(Product.category),
        )
        .where(Product.id == product_id)
    )
    return result.unique().scalar_one_or_none()


async def list_stores(session: AsyncSession, limit: int, offset: int) -> Sequence[Store]:
    result = await session.execute(
        select(Store)
        .join(Store.business)
        .options(contains_eager(Store.business).selectinload(Business.social_links))
        .where(Store.status == StoreStatus.ACTIVE, Business.status == BusinessStatus.ACTIVE)
        .order_by(Store.created_at.desc(), Store.id)
        .limit(limit)
        .offset(offset)
    )
    return result.unique().scalars().all()


async def count_stores(session: AsyncSession) -> int:
    result = await session.execute(
        select(func.count())
        .select_from(Store)
        .join(Store.business)
        .where(Store.status == StoreStatus.ACTIVE, Business.status == BusinessStatus.ACTIVE)
    )
    return result.scalar_one()


async def get_category_by_slug(session: AsyncSession, slug: str) -> Category | None:
    result = await session.execute(
        select(Category).where(Category.slug == slug, Category.status == CategoryStatus.ACTIVE)
    )
    return result.scalar_one_or_none()


async def list_child_ids(session: AsyncSession, parent_id: uuid.UUID) -> Sequence[uuid.UUID]:
    result = await session.execute(
        select(Category.id).where(
            Category.parent_id == parent_id, Category.status == CategoryStatus.ACTIVE
        )
    )
    return result.scalars().all()


async def list_categories(session: AsyncSession) -> Sequence[Category]:
    """The whole tree at once: it is two levels deep and changes about never."""
    result = await session.execute(
        select(Category)
        # the children are filtered too: hiding a subcategory must take it out of the
        # filter, not only out of its parent's listing
        .options(selectinload(Category.children.and_(Category.status == CategoryStatus.ACTIVE)))
        .where(Category.parent_id.is_(None), Category.status == CategoryStatus.ACTIVE)
        .order_by(Category.name)
    )
    return result.unique().scalars().all()
