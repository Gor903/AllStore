import uuid
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, Query, UploadFile, status

from app.core import storage
from app.deps.auth import SessionDep, SettingsDep, require_csrf
from app.deps.business import CurrentBusiness
from app.repositories import products as products_repo
from app.schemas.product import (
    ProductCreateRequest,
    ProductImageRead,
    ProductListResponse,
    ProductRead,
    ProductUpdateRequest,
)
from app.services import product_images as images_service
from app.services import products as products_service
from app.services import search_client

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
    payload: ProductCreateRequest,
    business: CurrentBusiness,
    session: SessionDep,
    background: BackgroundTasks,
    settings: SettingsDep,
) -> ProductRead:
    product = await products_service.create_product(session, business, payload)
    await session.commit()
    # the seller's answer does not wait for the search to catch up (docs/rag-first.md, раздел 25)
    background.add_task(search_client.product_changed, settings, product.id)
    return ProductRead.of(product)


@router.get("", response_model=ProductListResponse)
async def list_products(
    business: CurrentBusiness,
    session: SessionDep,
    limit: Limit = DEFAULT_PAGE_SIZE,
    offset: Offset = 0,
) -> ProductListResponse:
    items = await products_repo.list_for_business(session, business.id, limit, offset)
    return ProductListResponse(
        items=[ProductRead.of(item) for item in items],
        total=await products_repo.count_for_business(session, business.id),
        limit=limit,
        offset=offset,
    )


@router.get("/{product_id}", response_model=ProductRead)
async def read_product(
    product_id: uuid.UUID, business: CurrentBusiness, session: SessionDep
) -> ProductRead:
    product = await products_service.get_owned_product(session, business.id, product_id)
    return ProductRead.of(product)


@router.patch("/{product_id}", response_model=ProductRead, dependencies=[Depends(require_csrf)])
async def update_product(
    product_id: uuid.UUID,
    payload: ProductUpdateRequest,
    business: CurrentBusiness,
    session: SessionDep,
    background: BackgroundTasks,
    settings: SettingsDep,
) -> ProductRead:
    product = await products_service.update_product(session, business, product_id, payload)
    await session.commit()
    background.add_task(search_client.product_changed, settings, product.id)
    return ProductRead.of(product)


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


@router.post(
    "/{product_id}/submit", response_model=ProductRead, dependencies=[Depends(require_csrf)]
)
async def submit_product_for_review(
    product_id: uuid.UUID, business: CurrentBusiness, session: SessionDep
) -> ProductRead:
    """Sends the product back to the queue after a refusal, once the seller has fixed it."""
    product = await products_service.submit_product_for_review(session, business, product_id)
    await session.commit()
    return ProductRead.of(product)


@router.post(
    "/{product_id}/images",
    response_model=ProductImageRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_csrf)],
)
async def upload_product_image(
    product_id: uuid.UUID,
    business: CurrentBusiness,
    settings: SettingsDep,
    session: SessionDep,
    file: Annotated[UploadFile, File()],
    alt_text: Annotated[str | None, Form(max_length=255)] = None,
) -> ProductImageRead:
    image = await images_service.add_image(
        session, settings, business.id, product_id, file, alt_text
    )
    await session.commit()
    return ProductImageRead.model_validate(image)


@router.delete(
    "/{product_id}/images/{image_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_csrf)],
)
async def delete_product_image(
    product_id: uuid.UUID,
    image_id: uuid.UUID,
    business: CurrentBusiness,
    settings: SettingsDep,
    session: SessionDep,
) -> None:
    key = await images_service.remove_image(session, settings, business.id, product_id, image_id)
    await session.commit()
    # only after the row is gone for good: a deleted object under a surviving row would
    # show the buyer a broken picture, while a surviving object under no row costs storage
    if key is not None:
        await storage.delete_object(settings, key)
