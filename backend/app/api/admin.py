import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.core.errors import NotFoundError
from app.deps.auth import SessionDep, SettingsDep, require_csrf, require_role
from app.models import User, UserRole, UserStatus
from app.repositories import users as users_repo
from app.repositories.users import AccountFilter, AccountSort
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
from app.schemas.invitation import (
    InvitationCreated,
    InvitationCreateRequest,
    InvitationListResponse,
    InvitationRead,
)
from app.services import (
    account_blocks,
    admin_categories,
    admin_users,
    audit,
    invitations,
    permissions,
)

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
    role: Annotated[list[UserRole] | None, Query()] = None,
    status: Annotated[list[UserStatus] | None, Query()] = None,
    registered_from: Annotated[datetime | None, Query()] = None,
    registered_to: Annotated[datetime | None, Query()] = None,
    last_login_from: Annotated[datetime | None, Query()] = None,
    last_login_to: Annotated[datetime | None, Query()] = None,
    has_bans: Annotated[bool | None, Query()] = None,
    has_reports: Annotated[bool | None, Query()] = None,
    sort: AccountSort = AccountSort.REGISTERED,
    limit: Limit = DEFAULT_PAGE_SIZE,
    offset: Offset = 0,
) -> UserListResponse:
    """Everybody, narrowed however the administrator asks. `q` matches the address or the phone.

    An absent filter asks nothing; `has_bans=false` asks for the accounts that have never been
    barred, which is a different question from not asking.
    """
    where = AccountFilter(
        query=q,
        roles=role,
        statuses=status,
        registered_from=registered_from,
        registered_to=registered_to,
        last_login_from=last_login_from,
        last_login_to=last_login_to,
        has_bans=has_bans,
        has_reports=has_reports,
    )
    items, total = await admin_users.list_users(session, where, limit, offset, sort)
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


@router.get("/moderators", response_model=UserListResponse)
async def list_moderators(
    admin: AdminUser,
    session: SessionDep,
    q: SearchQuery = None,
    limit: Limit = DEFAULT_PAGE_SIZE,
    offset: Offset = 0,
) -> UserListResponse:
    """The moderator accounts themselves, as against the invitations that created them.

    They are not in `/accounts`: that list is about the people the platform serves. Barring a
    moderator is the same action under the same rank rule, taken here because here is where
    the administrator looks at moderators.
    """
    items, total = await account_blocks.list_in_scope(
        session, admin, permissions.Scope.STAFF, q, limit, offset
    )
    return UserListResponse(
        items=[UserRead.model_validate(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/moderator-invitations",
    response_model=InvitationCreated,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_csrf)],
)
async def invite_moderator(
    payload: InvitationCreateRequest,
    admin: AdminUser,
    settings: SettingsDep,
    session: SessionDep,
) -> InvitationCreated:
    """Issues the invitation and hands back its secret — the only time it is readable.

    It is stored as a sha256, so there is no second chance to look it up: an administrator
    who loses this answer revokes the invitation and issues another.
    """
    invitation, token = await invitations.create(session, admin, settings, payload.email)
    await session.commit()
    return InvitationCreated(invitation=InvitationRead.from_invitation(invitation), token=token)


@router.get("/moderator-invitations", response_model=InvitationListResponse)
async def list_moderator_invitations(
    _: AdminUser,
    session: SessionDep,
    limit: Limit = DEFAULT_PAGE_SIZE,
    offset: Offset = 0,
) -> InvitationListResponse:
    items, total = await invitations.list_all(session, limit, offset)
    return InvitationListResponse(
        items=[InvitationRead.from_invitation(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/moderator-invitations/{invitation_id}/revoke",
    response_model=InvitationRead,
    dependencies=[Depends(require_csrf)],
)
async def revoke_moderator_invitation(
    invitation_id: uuid.UUID, admin: AdminUser, session: SessionDep
) -> InvitationRead:
    invitation = await invitations.revoke(session, admin, invitation_id)
    await session.commit()
    return InvitationRead.from_invitation(invitation)


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
