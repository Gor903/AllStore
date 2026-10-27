import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.core.errors import NotFoundError
from app.deps.auth import SessionDep, require_csrf, require_role
from app.models import User, UserRole
from app.repositories import users as users_repo
from app.schemas.admin import (
    AdminCategoryRead,
    AuditLogListResponse,
    AuditLogRead,
    CategoryCreateRequest,
    CategoryUpdateRequest,
    RoleChangeRequest,
    UserListResponse,
)
from app.schemas.auth import UserRead
from app.services import admin_categories, admin_users, audit

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
    "/users/{user_id}/transfer-admin",
    response_model=UserRead,
    dependencies=[Depends(require_csrf)],
)
async def transfer_admin(user_id: uuid.UUID, admin: AdminUser, session: SessionDep) -> UserRead:
    """Hands over the one administrator role. The caller is a moderator when this returns.

    The platform has exactly one administrator, so there is no "appoint another" — the only
    way the role moves is as a whole, in one transaction, from the person asking to the person
    named. Blocking is not here at all: it is /accounts, where a moderator reaches it too.
    """
    successor = await admin_users.transfer_admin(session, admin, user_id)
    await session.commit()
    return UserRead.model_validate(successor)


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


@router.get("/categories", response_model=list[AdminCategoryRead])
async def list_categories(_: AdminUser, session: SessionDep) -> list[AdminCategoryRead]:
    tree = await admin_categories.list_tree(session)
    return [AdminCategoryRead.from_root(category) for category in tree]


@router.post(
    "/categories",
    response_model=AdminCategoryRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_csrf)],
)
async def create_category(
    payload: CategoryCreateRequest, admin: AdminUser, session: SessionDep
) -> AdminCategoryRead:
    category = await admin_categories.create(
        session, admin, payload.name, payload.slug, payload.parent_id
    )
    await session.commit()
    return AdminCategoryRead.leaf(category)


@router.patch(
    "/categories/{category_id}",
    response_model=AdminCategoryRead,
    dependencies=[Depends(require_csrf)],
)
async def update_category(
    category_id: uuid.UUID,
    payload: CategoryUpdateRequest,
    admin: AdminUser,
    session: SessionDep,
) -> AdminCategoryRead:
    category = None
    if payload.name is not None:
        category = await admin_categories.rename(session, admin, category_id, payload.name)
    if payload.status is not None:
        category = await admin_categories.set_status(session, admin, category_id, payload.status)
    if category is None:
        category = await admin_categories.find(session, category_id)
    await session.commit()
    return AdminCategoryRead.leaf(category)
