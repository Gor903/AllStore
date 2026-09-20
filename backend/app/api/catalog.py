import uuid
from typing import Annotated

from fastapi import APIRouter, Query

from app.deps.auth import SessionDep
from app.models.category import CATEGORY_SLUG_MAX_LENGTH
from app.models.store import SUBDOMAIN_MAX_LENGTH
from app.schemas.catalog import (
    CatalogProductListResponse,
    CatalogProductRead,
    CatalogStoreListResponse,
    CatalogStoreRead,
    CategoryTreeRead,
)
from app.services import catalog as catalog_service

router = APIRouter(prefix="/catalog", tags=["catalog"])

DEFAULT_PAGE_SIZE = 24
MAX_PAGE_SIZE = 100
QUERY_MAX_LENGTH = 100

Limit = Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)]
Offset = Annotated[int, Query(ge=0)]
SearchQuery = Annotated[str | None, Query(min_length=1, max_length=QUERY_MAX_LENGTH)]
CategorySlug = Annotated[str | None, Query(max_length=CATEGORY_SLUG_MAX_LENGTH)]
Subdomain = Annotated[str | None, Query(max_length=SUBDOMAIN_MAX_LENGTH)]


@router.get("/products", response_model=CatalogProductListResponse)
async def search_products(
    session: SessionDep,
    q: SearchQuery = None,
    category: CategorySlug = None,
    store: Subdomain = None,
    limit: Limit = DEFAULT_PAGE_SIZE,
    offset: Offset = 0,
) -> CatalogProductListResponse:
    items, total = await catalog_service.list_products(
        session, query=q, category_slug=category, subdomain=store, limit=limit, offset=offset
    )
    return CatalogProductListResponse(
        items=[CatalogProductRead.from_product(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/products/{product_id}", response_model=CatalogProductRead)
async def read_product(product_id: uuid.UUID, session: SessionDep) -> CatalogProductRead:
    return CatalogProductRead.from_product(await catalog_service.get_product(session, product_id))


@router.get("/stores", response_model=CatalogStoreListResponse)
async def list_stores(
    session: SessionDep, limit: Limit = DEFAULT_PAGE_SIZE, offset: Offset = 0
) -> CatalogStoreListResponse:
    items, total = await catalog_service.list_stores(session, limit, offset)
    return CatalogStoreListResponse(
        items=[CatalogStoreRead.from_store(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/categories", response_model=list[CategoryTreeRead])
async def list_categories(session: SessionDep) -> list[CategoryTreeRead]:
    categories = await catalog_service.list_categories(session)
    return [CategoryTreeRead.from_root(category) for category in categories]
