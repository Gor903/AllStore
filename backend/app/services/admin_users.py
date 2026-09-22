"""Administrative actions on accounts: who may act, and what each action leaves behind.

Two boundaries are drawn here rather than in the routes, because both protect the platform
from itself:

* the last administrator cannot be demoted or blocked — a platform with nobody able to
  appoint a moderator can only be repaired by hand in the database;
* an account that runs a shop is not touched here. Barring a seller is the business
  moderation flow (этап 5), which also takes the storefront off the air; doing it here
  would lock the owner out while their shop kept selling.
"""

import uuid
from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, NotFoundError, PermissionDeniedError
from app.models import User, UserRole, UserStatus
from app.repositories import users as users_repo
from app.services import audit

ENTITY = "user"


class UserNotFoundError(NotFoundError):
    code = "user_not_found"


class LastAdminError(ConflictError):
    code = "last_admin"


class SellerAccountError(ConflictError):
    code = "seller_account"


class AdminAccountError(PermissionDeniedError):
    code = "admin_account"


async def list_users(
    session: AsyncSession, query: str | None, limit: int, offset: int
) -> tuple[Sequence[User], int]:
    return (
        await users_repo.search(session, query, limit, offset),
        await users_repo.count_matching(session, query),
    )


async def change_role(
    session: AsyncSession, admin: User, user_id: uuid.UUID, role: UserRole
) -> User:
    user = await _find(session, user_id)
    if user.role is role:
        return user
    await _refuse_if_shopkeeper(session, user)
    if user.role is UserRole.ADMIN:
        await _refuse_if_last_admin(session, user)

    previous = user.role
    user.role = role
    await session.flush()
    # the role is read from the database on every request, so the new rights apply at once
    await audit.record(
        session, admin, "user.role_changed", ENTITY, user.id, **{"from": previous, "to": role}
    )
    return user


async def block(session: AsyncSession, admin: User, user_id: uuid.UUID, reason: str) -> User:
    user = await _find(session, user_id)
    if user.role is UserRole.ADMIN:
        raise AdminAccountError("Администратора нельзя заблокировать через этот экран")
    await _refuse_if_shopkeeper(session, user)

    user.status = UserStatus.BLOCKED
    await session.flush()
    await audit.record(session, admin, "user.blocked", ENTITY, user.id, reason=reason)
    return user


async def unblock(session: AsyncSession, admin: User, user_id: uuid.UUID) -> User:
    user = await _find(session, user_id)
    user.status = UserStatus.ACTIVE
    await session.flush()
    await audit.record(session, admin, "user.unblocked", ENTITY, user.id)
    return user


async def _find(session: AsyncSession, user_id: uuid.UUID) -> User:
    user = await users_repo.get_by_id(session, user_id)
    if user is None:
        raise UserNotFoundError("Пользователь не найден")
    return user


async def _refuse_if_last_admin(session: AsyncSession, user: User) -> None:
    if user.status is UserStatus.ACTIVE and await users_repo.count_active_admins(session) <= 1:
        raise LastAdminError(
            "Это последний администратор — сначала назначьте другого, иначе площадка "
            "останется без управления"
        )


async def _refuse_if_shopkeeper(session: AsyncSession, user: User) -> None:
    if await users_repo.get_business_of(session, user.id) is not None:
        raise SellerAccountError(
            "У этого аккаунта есть магазин: продавца блокируют в модерации бизнесов, "
            "иначе витрина останется в эфире без владельца"
        )
