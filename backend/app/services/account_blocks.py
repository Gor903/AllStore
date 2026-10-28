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
from app.repositories.users import AccountFilter
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
    session: AsyncSession, actor: User, user_id: uuid.UUID, limit: int, offset: int
) -> tuple[Sequence[AccountBlock], int]:
    target = await admin_users.find(session, user_id)
    # reading the record is reaching for the account: without this a moderator could read
    # another moderator's history by asking for it, having been refused the listing
    permissions.ensure_may_read(actor, target)
    return await blocks_repo.history(session, user_id, limit, offset)


async def list_in_scope(
    session: AsyncSession,
    actor: User,
    scope: permissions.Scope,
    query: str | None,
    limit: int,
    offset: int,
) -> tuple[Sequence[User], int]:
    """One screen's worth of accounts: who it is about, narrowed to who this actor may touch.

    The accounts screen holds buyers and sellers — for a moderator and for an administrator
    alike. Moderators are not people the platform serves but people who run it, and they live
    in the panel that is about running it.
    """
    where = AccountFilter(query=query, roles=permissions.listable_roles(actor.role, scope))
    return (
        await users_repo.search(session, where, limit, offset),
        await users_repo.count_matching(session, where),
    )
