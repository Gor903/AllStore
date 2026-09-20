import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.deps.auth import SessionDep, require_csrf, require_role
from app.models import User, UserRole
from app.schemas.moderation import ProductRejectRequest
from app.schemas.product import ProductListResponse, ProductRead
from app.services import moderation_queue

router = APIRouter(prefix="/moderation", tags=["moderation"])

# a moderator works across every tenant — the one role the isolation rule does not bind
ModeratorUser = Annotated[User, Depends(require_role(UserRole.MODERATOR, UserRole.ADMIN))]

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100

Limit = Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)]
Offset = Annotated[int, Query(ge=0)]


@router.get("/products", response_model=ProductListResponse)
async def read_queue(
    moderator: ModeratorUser,
    session: SessionDep,
    limit: Limit = DEFAULT_PAGE_SIZE,
    offset: Offset = 0,
) -> ProductListResponse:
    items, total = await moderation_queue.list_queue(session, limit, offset)
    return ProductListResponse(
        items=[ProductRead.model_validate(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/products/{product_id}/approve",
    response_model=ProductRead,
    dependencies=[Depends(require_csrf)],
)
async def approve_product(
    product_id: uuid.UUID, moderator: ModeratorUser, session: SessionDep
) -> ProductRead:
    product = await moderation_queue.approve(session, moderator, product_id)
    await session.commit()
    return ProductRead.model_validate(product)


@router.post(
    "/products/{product_id}/reject",
    response_model=ProductRead,
    dependencies=[Depends(require_csrf)],
)
async def reject_product(
    product_id: uuid.UUID,
    payload: ProductRejectRequest,
    moderator: ModeratorUser,
    session: SessionDep,
) -> ProductRead:
    product = await moderation_queue.reject(session, moderator, product_id, payload.reason)
    await session.commit()
    return ProductRead.model_validate(product)


@router.post(
    "/products/{product_id}/hide", response_model=ProductRead, dependencies=[Depends(require_csrf)]
)
async def hide_product(
    product_id: uuid.UUID, moderator: ModeratorUser, session: SessionDep
) -> ProductRead:
    product = await moderation_queue.hide(session, moderator, product_id)
    await session.commit()
    return ProductRead.model_validate(product)


@router.post(
    "/products/{product_id}/publish",
    response_model=ProductRead,
    dependencies=[Depends(require_csrf)],
)
async def publish_product(
    product_id: uuid.UUID, moderator: ModeratorUser, session: SessionDep
) -> ProductRead:
    """Takes back a hide — without it a moderator could not undo their own mistake."""
    product = await moderation_queue.publish(session, moderator, product_id)
    await session.commit()
    return ProductRead.model_validate(product)
