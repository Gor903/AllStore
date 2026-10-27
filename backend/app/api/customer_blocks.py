"""The shop's own door: who a seller will not serve, and who may look at that decision.

Three audiences, one table, so they live in one module rather than scattering a feature
across the seller, moderator and administrator routers:

* the seller manages the door of their own shop, and only their own — the tenant comes from
  the session, never from the path;
* staff read it. A shop that has barred half its customers is something the moderation queue
  should be able to notice;
* an administrator can open a door the seller closed, and the journal says they did.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.deps.auth import SessionDep, require_csrf, require_role
from app.deps.business import CurrentBusiness, SellerUser
from app.models import User, UserRole
from app.schemas.customer_block import (
    CustomerBlockListResponse,
    CustomerBlockRead,
    CustomerBlockRequest,
)
from app.services import customer_blocks

router = APIRouter(tags=["customer-blocks"])

SELLER_BLOCKS = "/stores/me/blocked-buyers"

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100

StaffUser = Annotated[User, Depends(require_role(UserRole.MODERATOR, UserRole.ADMIN))]
AdminUser = Annotated[User, Depends(require_role(UserRole.ADMIN))]
Limit = Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)]
Offset = Annotated[int, Query(ge=0)]


@router.get(SELLER_BLOCKS, response_model=CustomerBlockListResponse)
async def read_blocked_buyers(
    business: CurrentBusiness,
    session: SessionDep,
    limit: Limit = DEFAULT_PAGE_SIZE,
    offset: Offset = 0,
) -> CustomerBlockListResponse:
    items, total = await customer_blocks.list_for_business(session, business.id, limit, offset)
    return CustomerBlockListResponse(
        items=[CustomerBlockRead.from_block(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post(
    SELLER_BLOCKS,
    response_model=CustomerBlockRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_csrf)],
)
async def block_buyer(
    payload: CustomerBlockRequest,
    seller: SellerUser,
    business: CurrentBusiness,
    session: SessionDep,
) -> CustomerBlockRead:
    """Closes this shop to one buyer. Their account is untouched: they go on using the rest
    of the platform, and go on being able to complain about this shop."""
    created = await customer_blocks.block(session, business, seller, payload.email, payload.reason)
    await session.commit()
    await session.refresh(created, attribute_names=["buyer", "revoked_by"])
    return CustomerBlockRead.from_block(created)


@router.post(
    f"{SELLER_BLOCKS}/{{block_id}}/revoke",
    response_model=CustomerBlockRead,
    dependencies=[Depends(require_csrf)],
)
async def unblock_buyer(
    block_id: uuid.UUID,
    seller: SellerUser,
    business: CurrentBusiness,
    session: SessionDep,
) -> CustomerBlockRead:
    lifted = await customer_blocks.revoke(session, seller, block_id, business)
    await session.commit()
    await session.refresh(lifted, attribute_names=["buyer", "revoked_by"])
    return CustomerBlockRead.from_block(lifted)


@router.get("/accounts/{user_id}/store-blocks", response_model=CustomerBlockListResponse)
async def read_store_blocks_of_buyer(
    user_id: uuid.UUID,
    _: StaffUser,
    session: SessionDep,
    limit: Limit = DEFAULT_PAGE_SIZE,
    offset: Offset = 0,
) -> CustomerBlockListResponse:
    """Which shops have closed their door to this person, from the staff side."""
    items, total = await customer_blocks.list_for_buyer(session, user_id, limit, offset)
    return CustomerBlockListResponse(
        items=[CustomerBlockRead.from_block(item, with_store=True) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/store-blocks/{block_id}/revoke",
    response_model=CustomerBlockRead,
    dependencies=[Depends(require_csrf)],
)
async def revoke_store_block(
    block_id: uuid.UUID, admin: AdminUser, session: SessionDep
) -> CustomerBlockRead:
    """An administrator opening a door the seller closed. Recorded like any other decision."""
    lifted = await customer_blocks.revoke(session, admin, block_id, None)
    await session.commit()
    await session.refresh(lifted, attribute_names=["buyer", "revoked_by", "business"])
    return CustomerBlockRead.from_block(lifted, with_store=True)
