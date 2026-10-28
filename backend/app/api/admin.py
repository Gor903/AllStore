import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.core.errors import NotFoundError
from app.deps.auth import SessionDep, require_csrf, require_role
from app.models import User, UserRole, UserStatus
from app.repositories import users as users_repo
from app.repositories.audit import JournalFilter
from app.repositories.users import AccountFilter, AccountSort
from app.schemas.admin import (
    ActivityRead,
    AdminCategoryRead,
    AuditLogListResponse,
    AuditLogRead,
    CategoryCreateRequest,
    CategoryUpdateRequest,
    ModeratorCreateRequest,
    ModeratorPasswordRequest,
    ModeratorRecordRead,
    RoleChangeRequest,
    SystemStateRead,
    UserListResponse,
)
from app.schemas.auth import UserRead
from app.services import (
    account_blocks,
    admin_categories,
    admin_users,
    audit,
    moderator_record,
    moderators,
    permissions,
    system_health,
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
    """Everybody who moderates, and nobody else.

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
    "/moderators",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_csrf)],
)
async def create_moderator(
    payload: ModeratorCreateRequest, admin: AdminUser, session: SessionDep
) -> UserRead:
    """Makes the account and hands over a password the administrator chose.

    That password is known to the administrator, so it is not yet the moderator's: it gets
    them in once and the platform stays shut to them until they replace it.
    """
    moderator = await moderators.create(
        session, admin, payload.normalized_email, payload.password.get_secret_value()
    )
    await session.commit()
    return UserRead.model_validate(moderator)


@router.post(
    "/moderators/{user_id}/password",
    response_model=UserRead,
    dependencies=[Depends(require_csrf)],
)
async def reset_moderator_password(
    user_id: uuid.UUID,
    payload: ModeratorPasswordRequest,
    admin: AdminUser,
    session: SessionDep,
) -> UserRead:
    """The way back in for a moderator who lost theirs. The replacement expires the same way."""
    moderator = await moderators.reset_password(
        session, admin, user_id, payload.password.get_secret_value()
    )
    await session.commit()
    return UserRead.model_validate(moderator)


@router.get("/moderators/{user_id}", response_model=ModeratorRecordRead)
async def read_moderator(
    user_id: uuid.UUID, _: AdminUser, session: SessionDep
) -> ModeratorRecordRead:
    """What this moderator has decided, counted from the decisions themselves.

    Not from a tally kept beside them: a counter maintained in parallel can be wrong, and a
    wrong one here would be read as evidence.
    """
    return ModeratorRecordRead.of(await moderator_record.record_of(session, user_id))


@router.get("/audit-logs", response_model=AuditLogListResponse)
async def list_audit_logs(
    _: AdminUser,
    session: SessionDep,
    actor_id: uuid.UUID | None = None,
    action: Annotated[str | None, Query(min_length=1, max_length=64)] = None,
    since: Annotated[datetime | None, Query()] = None,
    until: Annotated[datetime | None, Query()] = None,
    limit: Limit = DEFAULT_PAGE_SIZE,
    offset: Offset = 0,
) -> AuditLogListResponse:
    """Administrator only: the journal names who did what, and that is not a moderator's.

    `action` matches by prefix, so `user.` asks for every decision about accounts without
    naming each of them — and the names stay free to grow.
    """
    where = JournalFilter(actor_id=actor_id, action=action, since=since, until=until)
    items, total = await audit.list_entries(session, where, limit, offset)
    return AuditLogListResponse(
        items=[AuditLogRead.from_entry(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/system", response_model=SystemStateRead)
async def read_system_state(_: AdminUser, session: SessionDep) -> SystemStateRead:
    """Read at the moment it is asked for: nothing here is stored, so nothing can go stale.

    Administrator only. The journal is not a moderator's and neither is this: knowing how
    loaded the machine is says nothing about moderating, and says a good deal about the
    platform to anybody who should not have it.
    """
    return SystemStateRead.of(system_health.resources(), await system_health.occupancy(session))


@router.get("/activity", response_model=ActivityRead)
async def read_activity(
    _: AdminUser,
    session: SessionDep,
    days: Annotated[int, Query(ge=1, le=90)] = 14,
) -> ActivityRead:
    """Registrations, logins, new products and complaints by day, aggregated on the spot."""
    return ActivityRead.of(await system_health.activity(session, days))


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
