import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.core.errors import NotFoundError
from app.deps.auth import SessionDep, require_csrf, require_role
from app.models import User, UserRole
from app.repositories import users as users_repo
from app.schemas.admin import (
    AuditLogListResponse,
    AuditLogRead,
    BlockRequest,
    RoleChangeRequest,
    UserListResponse,
)
from app.schemas.auth import UserRead
from app.services import admin_users, audit

router = APIRouter(prefix="/admin", tags=["admin"])

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100
QUERY_MAX_LENGTH = 320

AdminUser = Annotated[User, Depends(require_role(UserRole.ADMIN))]
Limit = Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)]
Offset = Annotated[int, Query(ge=0)]
SearchQuery = Annotated[str | None, Query(min_length=1, max_length=QUERY_MAX_LENGTH)]


@router.get("/users", response_model=UserListResponse)
async def list_users(
    _: AdminUser,
    session: SessionDep,
    q: SearchQuery = None,
    limit: Limit = DEFAULT_PAGE_SIZE,
    offset: Offset = 0,
) -> UserListResponse:
    items, total = await admin_users.list_users(session, q, limit, offset)
    return UserListResponse(
        items=[UserRead.model_validate(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/users/{user_id}", response_model=UserRead)
async def read_user(user_id: uuid.UUID, _: AdminUser, session: SessionDep) -> UserRead:
    user = await users_repo.get_by_id(session, user_id)
    if user is None:
        raise NotFoundError("Пользователь не найден")
    return UserRead.model_validate(user)


@router.post("/users/{user_id}/role", response_model=UserRead, dependencies=[Depends(require_csrf)])
async def change_role(
    user_id: uuid.UUID, payload: RoleChangeRequest, admin: AdminUser, session: SessionDep
) -> UserRead:
    user = await admin_users.change_role(session, admin, user_id, payload.role)
    await session.commit()
    return UserRead.model_validate(user)


@router.post(
    "/users/{user_id}/block", response_model=UserRead, dependencies=[Depends(require_csrf)]
)
async def block_user(
    user_id: uuid.UUID, payload: BlockRequest, admin: AdminUser, session: SessionDep
) -> UserRead:
    user = await admin_users.block(session, admin, user_id, payload.reason)
    await session.commit()
    return UserRead.model_validate(user)


@router.post(
    "/users/{user_id}/unblock", response_model=UserRead, dependencies=[Depends(require_csrf)]
)
async def unblock_user(user_id: uuid.UUID, admin: AdminUser, session: SessionDep) -> UserRead:
    user = await admin_users.unblock(session, admin, user_id)
    await session.commit()
    return UserRead.model_validate(user)


@router.get("/audit-logs", response_model=AuditLogListResponse)
async def list_audit_logs(
    _: AdminUser,
    session: SessionDep,
    limit: Limit = DEFAULT_PAGE_SIZE,
    offset: Offset = 0,
) -> AuditLogListResponse:
    """Administrator only: the journal names who did what, and that is not a moderator's."""
    items, total = await audit.list_entries(session, limit, offset)
    return AuditLogListResponse(
        items=[AuditLogRead.from_entry(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )
