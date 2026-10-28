"""Creating the first administrator, and only the first.

An empty platform has nobody who may appoint anybody, so the first administrator has to come
from outside the interface. That makes this the one place where authority is granted without
an actor to answer for it, and the rules are correspondingly narrow:

* it is idempotent — run it twice, three times, on every deploy, and the second run changes
  nothing and says so;
* it never overwrites the password of an existing account quietly. Restoring access to a
  locked-out administrator is a separate, deliberate ask (`reset_password=True`);
* it takes an advisory lock, so two deploys starting at once queue instead of colliding. The
  unique partial index on the admin role is the guarantee; the lock is what turns a crash into
  a sentence.

The environment is configuration, not a register: after the first run the database is the
authority on who administers the platform, and changing ADMIN_EMAIL afterwards does nothing.
"""

import enum
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.security import hash_password
from app.models import User, UserRole, UserStatus
from app.repositories import account_blocks as blocks_repo
from app.repositories import users as users_repo

# any constant will do, as long as every bootstrap uses the same one: this is a name for the
# queue, not a value anybody reads
BOOTSTRAP_LOCK_KEY = 0x4A11_5702


class Outcome(enum.StrEnum):
    CREATED = "created"
    PROMOTED = "promoted"
    PASSWORD_RESET = "password_reset"  # noqa: S105 — an outcome name, not a credential
    UNCHANGED = "unchanged"


@dataclass(frozen=True)
class Result:
    outcome: Outcome
    email: str

    @property
    def message(self) -> str:
        """What the operator reads. Never the password — not even the one just set."""
        return {
            Outcome.CREATED: f"{self.email}: администратор создан",
            Outcome.PROMOTED: f"{self.email}: существующий аккаунт стал администратором",
            Outcome.PASSWORD_RESET: f"{self.email}: пароль администратора заменён",
            Outcome.UNCHANGED: f"{self.email}: администратор уже есть, ничего не менялось",
        }[self.outcome]


class BootstrapNotConfiguredError(RuntimeError):
    pass


async def bootstrap(
    session: AsyncSession, email: str | None, password: str | None, *, reset_password: bool = False
) -> Result:
    if not email or not password:
        raise BootstrapNotConfiguredError(
            "ADMIN_EMAIL and ADMIN_PASSWORD must both be set to bootstrap an administrator"
        )
    await _queue_behind_other_bootstraps(session)

    normalized = email.strip().lower()
    admin = await users_repo.get_admin(session)
    if admin is not None:
        return await _keep_or_restore(session, admin, password, reset_password=reset_password)

    existing = await users_repo.get_by_email(session, normalized)
    if existing is not None:
        # an account that was a buyer yesterday becomes the administrator today; its password
        # is its own and stays that way
        existing.role = UserRole.ADMIN
        await _reactivate(session, existing)
        return Result(Outcome.PROMOTED, normalized)

    await users_repo.add(
        session,
        User(
            email=normalized,
            password_hash=hash_password(password),
            role=UserRole.ADMIN,
            # the password came out of a deploy variable, which is as good as written on a
            # wall: it gets the administrator in once, and then they choose their own
            must_change_password=True,
        ),
    )
    return Result(Outcome.CREATED, normalized)


async def _keep_or_restore(
    session: AsyncSession, admin: User, password: str, *, reset_password: bool
) -> Result:
    """The platform already has its administrator. The only thing left to offer is a way back
    in for the one who locked themselves out — and only when asked for in so many words."""
    if not reset_password:
        return Result(Outcome.UNCHANGED, admin.email)
    admin.password_hash = hash_password(password)
    # same reasoning as a fresh bootstrap: whoever holds the server now knows this password
    admin.must_change_password = True
    await _reactivate(session, admin)
    return Result(Outcome.PASSWORD_RESET, admin.email)


async def _reactivate(session: AsyncSession, user: User) -> None:
    """Letting an account back in means ending the ban, not just clearing the status: a row
    left in force would say the person is barred while the column says they are not."""
    in_force = await blocks_repo.get_in_force(session, user.id)
    if in_force is not None:
        in_force.revoked_at = datetime.now(UTC)
        in_force.revoke_reason = "Снята при восстановлении доступа администратора"
    user.status = UserStatus.ACTIVE
    await session.flush()


async def _queue_behind_other_bootstraps(session: AsyncSession) -> None:
    """Held until the transaction ends, so the next runner reads what this one wrote."""
    await session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": BOOTSTRAP_LOCK_KEY})


async def bootstrap_on_startup(session: AsyncSession, settings: Settings) -> str | None:
    """The same thing the deploy script does, done by the application coming up.

    Returns what happened, for the log, or None when there is nothing configured to do. An
    unset ADMIN_EMAIL is not a misconfiguration — a stand or a test run has no administrator
    and wants none — so the absence is quiet and the application still starts. A database
    that refuses the write is a different matter and is left to propagate.
    """
    if not settings.admin_email or settings.admin_password is None:
        return None
    result = await bootstrap(
        session, settings.admin_email, settings.admin_password.get_secret_value()
    )
    await session.commit()
    return result.message
