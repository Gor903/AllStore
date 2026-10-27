"""Barring an account, and the history of every time it happened.

One route group rather than one per panel. Blocking is a single action in the access matrix —
a moderator may bar buyers and sellers, an administrator may bar moderators too — and who may
do it to whom is decided by rank in `services/permissions.py`, not by which URL was called.
Two endpoints doing the same thing under different prefixes would be two places for that rule
to drift apart.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.deps.auth import SessionDep, require_csrf, require_role
from app.models import User, UserRole
from app.schemas.account import (
    AccountBlockListResponse,
    AccountBlockRead,
    BlockRequest,
    UnblockRequest,
)
from app.schemas.auth import UserRead
from app.services import account_blocks

router = APIRouter(prefix="/accounts", tags=["accounts"])

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100

StaffUser = Annotated[User, Depends(require_role(UserRole.MODERATOR, UserRole.ADMIN))]
Limit = Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)]
Offset = Annotated[int, Query(ge=0)]


@router.post("/{user_id}/block", response_model=UserRead, dependencies=[Depends(require_csrf)])
async def block_account(
    user_id: uuid.UUID, payload: BlockRequest, actor: StaffUser, session: SessionDep
) -> UserRead:
    user = await account_blocks.block(session, actor, user_id, payload.reason)
    await session.commit()
    return UserRead.model_validate(user)


@router.post("/{user_id}/unblock", response_model=UserRead, dependencies=[Depends(require_csrf)])
async def unblock_account(
    user_id: uuid.UUID, payload: UnblockRequest, actor: StaffUser, session: SessionDep
) -> UserRead:
    user = await account_blocks.unblock(session, actor, user_id, payload.reason)
    await session.commit()
    return UserRead.model_validate(user)


@router.get("/{user_id}/blocks", response_model=AccountBlockListResponse)
async def read_block_history(
    user_id: uuid.UUID,
    _: StaffUser,
    session: SessionDep,
    limit: Limit = DEFAULT_PAGE_SIZE,
    offset: Offset = 0,
) -> AccountBlockListResponse:
    """Every ban this account has ever had, lifted or not. A ban that is taken back still
    happened, and the next moderator deciding about this person needs to know it did."""
    items, total = await account_blocks.history(session, user_id, limit, offset)
    return AccountBlockListResponse(
        items=[AccountBlockRead.from_block(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )
