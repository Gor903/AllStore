import uuid
from collections.abc import Sequence
from typing import Any

from sqlalchemy import ColumnElement, Select, and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import contains_eager, selectinload

from app.models import (
    Business,
    BusinessCustomerBlock,
    BusinessStatus,
    Category,
    CategoryStatus,
    ModerationStatus,
    Product,
    PublicationStatus,
    Store,
    StoreStatus,
    User,
    UserStatus,
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
    # the owner too: barring a seller has to take their shelf down with them, and a status
    # copied onto the business would be a second thing to keep in step and a window in which
    # the account is gone and the shop is still selling
    User.status == UserStatus.ACTIVE,
)

# every public query joins the same three tables, because PUBLIC_PRODUCT names all three
PUBLIC_JOIN = (Product.business, Business.owner, Business.store)

# the same rule one level up: a shop is listed while the shop, the business and the person
# behind it are all in good standing
PUBLIC_STORE = (
    Store.status == StoreStatus.ACTIVE,
    Business.status == BusinessStatus.ACTIVE,
    User.status == UserStatus.ACTIVE,
)


def visible_to(viewer_id: uuid.UUID | None) -> ColumnElement[bool]:
    """The one condition that depends on who is asking: a shop that has barred this buyer.

    A seller may decide who is welcome in their own shop. Applied here rather than in each
    route, so the shop disappears from the listing, from the search, from the storefront and
    from a saved link in one stroke — instead of in whichever places somebody remembered.

    A guest is barred by nobody, so the clause folds away and the query is the one every
    anonymous visitor has always run.
    """
    if viewer_id is None:
        return and_(True)
    return (
        ~select(BusinessCustomerBlock.id)
        .where(
            BusinessCustomerBlock.business_id == Business.id,
            BusinessCustomerBlock.buyer_user_id == viewer_id,
            BusinessCustomerBlock.revoked_at.is_(None),
        )
        .exists()
    )


def like_pattern(query: str) -> str:
    """% and _ are wildcards, so a query containing them must not widen the search."""
    escaped = (
        query.replace(LIKE_ESCAPE, LIKE_ESCAPE * 2)
        .replace("%", f"{LIKE_ESCAPE}%")
        .replace("_", f"{LIKE_ESCAPE}_")
    )
    return f"%{escaped}%"


def with_public_joins[S: Select[Any]](statement: S) -> S:
    """The joins PUBLIC_PRODUCT needs, added in one call.

    Public because every query filtering on PUBLIC_PRODUCT needs exactly these. A second
    place spelling the joins out by hand is a second place to miss one when the rule grows a
    table — which is what happened to the complaint form when the owner's status joined it.
    """
    for relationship in PUBLIC_JOIN:
        statement = statement.join(relationship)
    return statement


def _public_products(viewer_id: uuid.UUID | None) -> Select[tuple[Product]]:
    return with_public_joins(select(Product)).where(*PUBLIC_PRODUCT, visible_to(viewer_id))


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
                # buyers search by the shop too: asking what a particular workshop sells is a
                # question about products, not about shops (AllStore_build_plan.md, item 11.8)
                Business.display_name.ilike(pattern, escape=LIKE_ESCAPE),
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
    viewer_id: uuid.UUID | None,
) -> Sequence[Product]:
    statement = _narrow(_public_products(viewer_id), query, category_ids, subdomain)
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
    viewer_id: uuid.UUID | None,
) -> list[uuid.UUID]:
    """Identifiers of the exact matches, newest first — the same set the listing shows.

    Used when the ordering has to be merged with another one; loading whole products only to
    throw most of them away would be the alternative.
    """
    statement = _narrow(
        with_public_joins(select(Product.id)).where(*PUBLIC_PRODUCT, visible_to(viewer_id)),
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
    viewer_id: uuid.UUID | None,
) -> set[uuid.UUID]:
    """Which of these products a visitor may actually see.

    The search index knows nothing about moderation, publication or a shop being off the air —
    and must not. This is where identifiers from anywhere meet the one rule that decides
    visibility, the same `PUBLIC_PRODUCT` the listing itself is built on.
    """
    if not ids:
        return set()
    statement = _narrow(
        with_public_joins(select(Product.id)).where(
            *PUBLIC_PRODUCT, visible_to(viewer_id), Product.id.in_(ids)
        ),
        None,
        category_ids,
        subdomain,
    )
    return set((await session.execute(statement)).scalars().all())


async def list_products_by_ids(
    session: AsyncSession, ids: Sequence[uuid.UUID], viewer_id: uuid.UUID | None
) -> Sequence[Product]:
    """The products behind an already-decided order; the caller restores that order."""
    if not ids:
        return []
    result = await session.execute(
        _public_products(viewer_id)
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
    viewer_id: uuid.UUID | None,
) -> int:
    statement = _narrow(
        with_public_joins(select(func.count()).select_from(Product)).where(
            *PUBLIC_PRODUCT, visible_to(viewer_id)
        ),
        query,
        category_ids,
        subdomain,
    )
    return (await session.execute(statement)).scalar_one()


async def get_product(
    session: AsyncSession, product_id: uuid.UUID, viewer_id: uuid.UUID | None
) -> Product | None:
    result = await session.execute(
        _public_products(viewer_id)
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


async def list_stores(
    session: AsyncSession, limit: int, offset: int, viewer_id: uuid.UUID | None
) -> Sequence[Store]:
    result = await session.execute(
        select(Store)
        .join(Store.business)
        .join(Business.owner)
        .options(contains_eager(Store.business).selectinload(Business.social_links))
        .where(*PUBLIC_STORE, visible_to(viewer_id))
        .order_by(Store.created_at.desc(), Store.id)
        .limit(limit)
        .offset(offset)
    )
    return result.unique().scalars().all()


async def count_stores(session: AsyncSession, viewer_id: uuid.UUID | None) -> int:
    result = await session.execute(
        select(func.count())
        .select_from(Store)
        .join(Store.business)
        .join(Business.owner)
        .where(*PUBLIC_STORE, visible_to(viewer_id))
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
