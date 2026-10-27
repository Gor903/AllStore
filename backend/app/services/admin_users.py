"""Administrative actions on accounts: who may act, and what each action leaves behind.

Who may act on whom is not decided here — it is one table, `services/permissions.py`, and this
module asks it. What is decided here is what the platform must never be left in:

* there is exactly one administrator, and no route creates a second or removes the only one.
  Handing the role over is therefore a move, not two edits: `transfer_admin` demotes and
  promotes inside one transaction, so the platform is never without an administrator and never
  has two;
* an account that runs a shop does not change role here. Its storefront would go on selling
  under an owner the dashboard no longer lets in. Barring such a seller is a different action —
  `services/account_blocks.py` — which takes the shop off the air along with the account.
"""

import uuid
from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, NotFoundError
from app.models import User, UserRole
from app.repositories import users as users_repo
from app.services import audit, permissions

ENTITY = "user"


class UserNotFoundError(NotFoundError):
    code = "user_not_found"


class LastAdminError(ConflictError):
    code = "last_admin"


class SellerAccountError(ConflictError):
    code = "seller_account"


class AdminAccountError(ConflictError):
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
    user = await find(session, user_id)
    if user.role is role:
        return user
    _refuse_if_administrator(admin, user)
    permissions.ensure_may_change_role(admin, user)
    if role is UserRole.ADMIN:
        raise AdminAccountError(
            "Администратор на площадке один. Чтобы передать эту роль, используйте передачу "
            "администрирования — она снимает роль с вас и отдаёт её в одно действие"
        )
    await _refuse_if_shopkeeper(session, user)

    previous = user.role
    user.role = role
    await session.flush()
    # the role is read from the database on every request, so the new rights apply at once
    await audit.record(
        session, admin, "user.role_changed", ENTITY, user.id, **{"from": previous, "to": role}
    )
    return user


async def transfer_admin(session: AsyncSession, admin: User, user_id: uuid.UUID) -> User:
    """Hands the one administrator role to somebody else, in one transaction.

    The outgoing administrator becomes a moderator rather than a buyer: handing over the keys
    is a move between people who run the platform, not a resignation from it, and the journal
    says who did it either way.
    """
    successor = await find(session, user_id)
    if successor.id == admin.id:
        raise AdminAccountError("Вы уже администратор")
    if successor.role is UserRole.ADMIN:
        raise AdminAccountError("Этот аккаунт уже администратор")
    if not successor.is_active:
        raise AdminAccountError("Нельзя передать администрирование заблокированному аккаунту")
    await _refuse_if_shopkeeper(session, successor)

    # demoted first and flushed on its own: the unique index allows one admin row at a time,
    # so the seat has to be empty before the successor takes it
    admin.role = UserRole.MODERATOR
    await session.flush()
    successor.role = UserRole.ADMIN
    await session.flush()
    await audit.record(
        session, admin, "user.admin_transferred", ENTITY, successor.id, to=successor.email
    )
    return successor


async def find(session: AsyncSession, user_id: uuid.UUID) -> User:
    user = await users_repo.get_by_id(session, user_id)
    if user is None:
        raise UserNotFoundError("Пользователь не найден")
    return user


def _refuse_if_administrator(admin: User, user: User) -> None:
    """Said in its own words rather than as a missing right: an administrator reaching for
    their own role is asking for the handover, and deserves to be pointed at it."""
    if user.role is UserRole.ADMIN:
        raise LastAdminError(
            "Это единственный администратор — роль у него не снимают, её передают другому "
            "аккаунту, иначе площадка останется без управления"
        )


async def _refuse_if_shopkeeper(session: AsyncSession, user: User) -> None:
    if await users_repo.get_business_of(session, user.id) is not None:
        raise SellerAccountError(
            "У этого аккаунта есть магазин: роль продавца здесь не меняют, иначе витрина "
            "останется в эфире под владельцем, которого в кабинет уже не пускают"
        )
