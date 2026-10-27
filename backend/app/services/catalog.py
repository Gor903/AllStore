import uuid
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import NotFoundError
from app.models import Category, Product, Store
from app.repositories import catalog
from app.services import ranking, search_client
from app.services.products import ProductNotFoundError

# how many exact matches take part in the merge: beyond this a text query is not a search
# any more, and the visitor is going to refine it rather than page through five hundred items
EXACT_CANDIDATES = 500


class UnknownCategoryError(NotFoundError):
    code = "category_not_found"


@dataclass(frozen=True)
class CatalogPage:
    items: Sequence[Product]
    total: int
    # what only the semantic search found: the words of the query are not in these products,
    # and a buyer deserves to be told why they are in the list
    by_meaning: set[uuid.UUID]


async def list_products(
    session: AsyncSession,
    *,
    query: str | None,
    category_slug: str | None,
    subdomain: str | None,
    limit: int,
    offset: int,
    settings: Settings | None = None,
    viewer_id: uuid.UUID | None = None,
) -> CatalogPage:
    category_ids = None if category_slug is None else await _with_children(session, category_slug)
    if query is not None and settings is not None and settings.search_service_url is not None:
        return await _search_by_words_and_meaning(
            session,
            settings=settings,
            query=query,
            category_ids=category_ids,
            subdomain=subdomain,
            limit=limit,
            offset=offset,
            viewer_id=viewer_id,
        )
    return CatalogPage(
        items=await catalog.list_products(
            session,
            query=query,
            category_ids=category_ids,
            subdomain=subdomain,
            limit=limit,
            offset=offset,
            viewer_id=viewer_id,
        ),
        total=await catalog.count_products(
            session,
            query=query,
            category_ids=category_ids,
            subdomain=subdomain,
            viewer_id=viewer_id,
        ),
        by_meaning=set(),
    )


async def _search_by_words_and_meaning(
    session: AsyncSession,
    *,
    settings: Settings,
    query: str,
    category_ids: Sequence[uuid.UUID] | None,
    subdomain: str | None,
    limit: int,
    offset: int,
    viewer_id: uuid.UUID | None,
) -> CatalogPage:
    """Both searches, one list.

    The exact search is authoritative about what contains the words; the semantic one is
    authoritative about nothing, only suggestive. They are merged by rank rather than by score
    (see services/ranking.py), and the result meets the public filter afterwards — identifiers
    from the index have no standing until this repository confirms a visitor may see them.

    `total` here counts the merged candidates rather than every product that would ever match:
    a semantic search has no natural total, and a page count that grew when a service came up
    would be stranger than one that says how much this search found.
    """
    exact = await catalog.list_matching_ids(
        session,
        query=query,
        category_ids=category_ids,
        subdomain=subdomain,
        limit=EXACT_CANDIDATES,
        viewer_id=viewer_id,
    )
    found_by_meaning = await search_client.semantic_ids(settings, query, settings.search_candidates)
    merged = ranking.merge(exact, found_by_meaning)
    public = await catalog.keep_public(
        session, merged, category_ids=category_ids, subdomain=subdomain, viewer_id=viewer_id
    )
    ordered = [identifier for identifier in merged if identifier in public]

    page = ordered[offset : offset + limit]
    products = {
        product.id: product
        for product in await catalog.list_products_by_ids(session, page, viewer_id)
    }
    return CatalogPage(
        items=[products[identifier] for identifier in page if identifier in products],
        total=len(ordered),
        by_meaning=public.intersection(found_by_meaning).difference(exact),
    )


async def get_product(
    session: AsyncSession, product_id: uuid.UUID, viewer_id: uuid.UUID | None = None
) -> Product:
    """A product that is not public answers exactly as one that does not exist.

    A shop that has barred this buyer is not public *to them*, so a saved link answers the
    same 404 as a product that was taken down — the filter decides, not the route.
    """
    product = await catalog.get_product(session, product_id, viewer_id)
    if product is None:
        raise ProductNotFoundError("Товар не найден")
    return product


async def list_stores(
    session: AsyncSession, limit: int, offset: int, viewer_id: uuid.UUID | None = None
) -> tuple[Sequence[Store], int]:
    return (
        await catalog.list_stores(session, limit, offset, viewer_id),
        await catalog.count_stores(session, viewer_id),
    )


async def list_categories(session: AsyncSession) -> Sequence[Category]:
    return await catalog.list_categories(session)


async def _with_children(session: AsyncSession, slug: str) -> list[uuid.UUID]:
    """A top-level category stands for everything filed under it — that is what a shopper means."""
    category = await catalog.get_category_by_slug(session, slug)
    if category is None:
        raise UnknownCategoryError("Категория не найдена")
    return [category.id, *await catalog.list_child_ids(session, category.id)]
