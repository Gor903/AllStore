"""Appointing a moderator: the administrator makes the account and hands over a password.

A moderator judges other people's shops and bars other people's accounts, so the role is not
something a form on the public site can grant. There is exactly one way in, and it starts
with an administrator typing an address.

The password the administrator types is known to the administrator, which means it is not yet
anybody's: it gets the moderator in once, and the platform stays shut to them until they
replace it. That is the same rule as an administrator bootstrapped from the environment and
an account created by `scripts.grant_role`, and it is the whole reason the password here may
be handed over in a chat message without the role being handed over with it.
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError
from app.core.security import hash_password
from app.models import User, UserRole
from app.repositories import users as users_repo
from app.services import audit, moderator_record, permissions

ENTITY = "user"


class AccountExistsError(ConflictError):
    code = "account_exists"


async def create(session: AsyncSession, admin: User, email: str, password: str) -> User:
    """Creates the moderator. The caller owns the commit."""
    permissions.ensure_may_appoint_moderator(admin)
    normalized = email.strip().lower()
    if await users_repo.get_by_email(session, normalized) is not None:
        # said plainly: this is the administrator's own panel, and an address they cannot see
        # the state of is an address they cannot act on
        raise AccountExistsError("Аккаунт с таким адресом уже есть")

    moderator = await users_repo.add(
        session,
        User(
            email=normalized,
            password_hash=hash_password(password),
            role=UserRole.MODERATOR,
            # handed over, therefore temporary — see the module docstring
            must_change_password=True,
        ),
    )
    await audit.record(session, admin, "moderator.created", ENTITY, moderator.id, email=normalized)
    return moderator


async def reset_password(
    session: AsyncSession, admin: User, user_id: uuid.UUID, password: str
) -> User:
    """A moderator who lost their password gets a new temporary one, not a recovery link.

    The administrator already decides who moderates; letting them restore access is no new
    authority. The replacement expires on first use exactly like the first one did.
    """
    permissions.ensure_may_appoint_moderator(admin)
    # an account that is not a moderator has no password for this screen to reset, and
    # whether it exists at all is not this screen's business — see moderator_record
    moderator = await moderator_record.find_moderator(session, user_id)
    moderator.password_hash = hash_password(password)
    moderator.must_change_password = True
    await session.flush()
    await audit.record(session, admin, "moderator.password_reset", ENTITY, moderator.id)
    return moderator
