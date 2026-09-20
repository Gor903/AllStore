import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.deps.auth import SessionDep, require_csrf
from app.deps.business import CurrentBusiness
from app.repositories import products as products_repo
from app.schemas.product import (
    ProductCreateRequest,
    ProductListResponse,
    ProductRead,
    ProductUpdateRequest,
)
from app.services import products as products_service

router = APIRouter(prefix="/products", tags=["products"])

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100

Limit = Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)]
Offset = Annotated[int, Query(ge=0)]


@router.post(
    "",
    response_model=ProductRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_csrf)],
)
async def create_product(
    payload: ProductCreateRequest, business: CurrentBusiness, session: SessionDep
) -> ProductRead:
    product = await products_service.create_product(session, business, payload)
    await session.commit()
    return ProductRead.model_validate(product)


@router.get("", response_model=ProductListResponse)
async def list_products(
    business: CurrentBusiness,
    session: SessionDep,
    limit: Limit = DEFAULT_PAGE_SIZE,
    offset: Offset = 0,
) -> ProductListResponse:
    items = await products_repo.list_for_business(session, business.id, limit, offset)
    return ProductListResponse(
        items=[ProductRead.model_validate(item) for item in items],
        total=await products_repo.count_for_business(session, business.id),
        limit=limit,
        offset=offset,
    )


@router.get("/{product_id}", response_model=ProductRead)
async def read_product(
    product_id: uuid.UUID, business: CurrentBusiness, session: SessionDep
) -> ProductRead:
    product = await products_service.get_owned_product(session, business.id, product_id)
    return ProductRead.model_validate(product)


@router.patch("/{product_id}", response_model=ProductRead, dependencies=[Depends(require_csrf)])
async def update_product(
    product_id: uuid.UUID,
    payload: ProductUpdateRequest,
    business: CurrentBusiness,
    session: SessionDep,
) -> ProductRead:
    product = await products_service.update_product(session, business.id, product_id, payload)
    await session.commit()
    return ProductRead.model_validate(product)


@router.delete(
    "/{product_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_csrf)],
)
async def archive_product(
    product_id: uuid.UUID, business: CurrentBusiness, session: SessionDep
) -> None:
    """Archives rather than deletes — see app.services.products.archive_product."""
    await products_service.archive_product(session, business.id, product_id)
    await session.commit()
