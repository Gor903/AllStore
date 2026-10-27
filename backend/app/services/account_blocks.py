"""Barring an account from the platform, and letting it back in.

A ban here is global: the person cannot sign in or use any authorized route until it is
lifted. It is deliberately not a deletion and not a cascade — the account, its shop, its
products, the complaints about it and every verdict ever passed on it stay exactly where they
were. What changes is one status, and a row in `account_blocks` saying who changed it and why.

A barred seller's storefront goes dark without anybody taking it off the air by hand: the
public catalogue filters on the owner's status as well as the shop's (see
`repositories/catalog.py`), so there is no second state to keep in step and no window in which
the account is gone and the shelf is still selling.
"""

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError
from app.models import AccountBlock, User, UserStatus
from app.repositories import account_blocks as blocks_repo
from app.repositories import auth_tokens
from app.repositories import users as users_repo
from app.services import admin_users, audit, permissions

ENTITY = "user"


class AlreadyBlockedError(ConflictError):
    code = "already_blocked"


class NotBlockedError(ConflictError):
    code = "not_blocked"


async def block(session: AsyncSession, actor: User, user_id: uuid.UUID, reason: str) -> User:
    target = await admin_users.find(session, user_id)
    permissions.ensure_may_block(actor, target)
    if await blocks_repo.get_in_force(session, target.id) is not None:
        raise AlreadyBlockedError("Этот аккаунт уже заблокирован")

    target.status = UserStatus.BLOCKED
    await blocks_repo.add(
        session, AccountBlock(user_id=target.id, actor_user_id=actor.id, reason=reason)
    )
    # the access token stays valid for minutes, so the status alone would be enough; revoking
    # the refresh tokens is what stops the session from quietly renewing itself afterwards
    await auth_tokens.revoke_all_for_user(session, target.id)
    await session.flush()
    await audit.record(session, actor, "user.blocked", ENTITY, target.id, reason=reason)
    return target


async def unblock(
    session: AsyncSession, actor: User, user_id: uuid.UUID, reason: str | None = None
) -> User:
    """Lifting a ban ends it, it does not erase it: the row stays and gains who closed it."""
    target = await admin_users.find(session, user_id)
    permissions.ensure_may_block(actor, target)
    in_force = await blocks_repo.get_in_force(session, target.id)
    if in_force is None and target.is_active:
        raise NotBlockedError("Этот аккаунт не заблокирован")

    target.status = UserStatus.ACTIVE
    if in_force is not None:
        in_force.revoked_at = datetime.now(UTC)
        in_force.revoked_by_user_id = actor.id
        in_force.revoke_reason = reason
    await session.flush()
    # an absent reason is absent from the entry rather than recorded as an empty one
    details = {} if reason is None else {"reason": reason}
    await audit.record(session, actor, "user.unblocked", ENTITY, target.id, **details)
    return target


async def history(
    session: AsyncSession, user_id: uuid.UUID, limit: int, offset: int
) -> tuple[Sequence[AccountBlock], int]:
    await admin_users.find(session, user_id)
    return await blocks_repo.history(session, user_id, limit, offset)


async def list_reachable(
    session: AsyncSession, actor: User, query: str | None, limit: int, offset: int
) -> tuple[Sequence[User], int]:
    """The accounts this actor may actually do something about.

    A moderator's list holds buyers and sellers, an administrator's holds moderators too.
    Filtered from the same ranks the individual checks use, so the screen offers exactly the
    rows whose buttons will work rather than rows that answer 403 when pressed.
    """
    roles = permissions.reachable_roles(actor.role)
    return (
        await users_repo.search(session, query, limit, offset, roles),
        await users_repo.count_matching(session, query, roles),
    )
