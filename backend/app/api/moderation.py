import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.deps.auth import SessionDep, require_csrf, require_role
from app.models import User, UserRole
from app.schemas.moderation import (
    BusinessListResponse,
    BusinessReviewRead,
    ModerationProductListResponse,
    ModerationProductRead,
    ModerationReasonRequest,
)
from app.services import business_moderation, moderation_queue

router = APIRouter(prefix="/moderation", tags=["moderation"])

# a moderator works across every tenant — the one role the isolation rule does not bind
ModeratorUser = Annotated[User, Depends(require_role(UserRole.MODERATOR, UserRole.ADMIN))]

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100

Limit = Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)]
Offset = Annotated[int, Query(ge=0)]


@router.get("/products", response_model=ModerationProductListResponse)
async def read_queue(
    moderator: ModeratorUser,
    session: SessionDep,
    limit: Limit = DEFAULT_PAGE_SIZE,
    offset: Offset = 0,
) -> ModerationProductListResponse:
    items, total = await moderation_queue.list_queue(session, limit, offset)
    return ModerationProductListResponse(
        items=[ModerationProductRead.from_product(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/products/{product_id}/approve",
    response_model=ModerationProductRead,
    dependencies=[Depends(require_csrf)],
)
async def approve_product(
    product_id: uuid.UUID, moderator: ModeratorUser, session: SessionDep
) -> ModerationProductRead:
    product = await moderation_queue.approve(session, moderator, product_id)
    await session.commit()
    return ModerationProductRead.from_product(product)


@router.post(
    "/products/{product_id}/reject",
    response_model=ModerationProductRead,
    dependencies=[Depends(require_csrf)],
)
async def reject_product(
    product_id: uuid.UUID,
    payload: ModerationReasonRequest,
    moderator: ModeratorUser,
    session: SessionDep,
) -> ModerationProductRead:
    product = await moderation_queue.reject(session, moderator, product_id, payload.reason)
    await session.commit()
    return ModerationProductRead.from_product(product)


@router.post(
    "/products/{product_id}/hide",
    response_model=ModerationProductRead,
    dependencies=[Depends(require_csrf)],
)
async def hide_product(
    product_id: uuid.UUID, moderator: ModeratorUser, session: SessionDep
) -> ModerationProductRead:
    product = await moderation_queue.hide(session, moderator, product_id)
    await session.commit()
    return ModerationProductRead.from_product(product)


@router.post(
    "/products/{product_id}/publish",
    response_model=ModerationProductRead,
    dependencies=[Depends(require_csrf)],
)
async def publish_product(
    product_id: uuid.UUID, moderator: ModeratorUser, session: SessionDep
) -> ModerationProductRead:
    """Takes back a hide — without it a moderator could not undo their own mistake."""
    product = await moderation_queue.publish(session, moderator, product_id)
    await session.commit()
    return ModerationProductRead.from_product(product)


@router.get("/businesses", response_model=BusinessListResponse)
async def read_business_queue(
    moderator: ModeratorUser,
    session: SessionDep,
    limit: Limit = DEFAULT_PAGE_SIZE,
    offset: Offset = 0,
) -> BusinessListResponse:
    items, total = await business_moderation.list_pending(session, limit, offset)
    return BusinessListResponse(
        items=[BusinessReviewRead.from_business(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/businesses/{business_id}/approve",
    response_model=BusinessReviewRead,
    dependencies=[Depends(require_csrf)],
)
async def approve_business(
    business_id: uuid.UUID, moderator: ModeratorUser, session: SessionDep
) -> BusinessReviewRead:
    """Admission: from here the storefront answers on its subdomain."""
    business = await business_moderation.approve(session, moderator, business_id)
    await session.commit()
    return BusinessReviewRead.from_business(business)


@router.post(
    "/businesses/{business_id}/suspend",
    response_model=BusinessReviewRead,
    dependencies=[Depends(require_csrf)],
)
async def suspend_business(
    business_id: uuid.UUID,
    payload: ModerationReasonRequest,
    moderator: ModeratorUser,
    session: SessionDep,
) -> BusinessReviewRead:
    business = await business_moderation.suspend(session, moderator, business_id, payload.reason)
    await session.commit()
    return BusinessReviewRead.from_business(business)


@router.post(
    "/businesses/{business_id}/block",
    response_model=BusinessReviewRead,
    dependencies=[Depends(require_csrf)],
)
async def block_business(
    business_id: uuid.UUID,
    payload: ModerationReasonRequest,
    moderator: ModeratorUser,
    session: SessionDep,
) -> BusinessReviewRead:
    business = await business_moderation.block(session, moderator, business_id, payload.reason)
    await session.commit()
    return BusinessReviewRead.from_business(business)


@router.post(
    "/businesses/{business_id}/restore",
    response_model=BusinessReviewRead,
    dependencies=[Depends(require_csrf)],
)
async def restore_business(
    business_id: uuid.UUID, moderator: ModeratorUser, session: SessionDep
) -> BusinessReviewRead:
    """A ban is a status, not a deletion, so it can be taken back."""
    business = await business_moderation.restore(session, moderator, business_id)
    await session.commit()
    return BusinessReviewRead.from_business(business)
