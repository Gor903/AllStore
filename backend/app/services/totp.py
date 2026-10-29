"""Enrolling a second factor, and answering with it.

Who needs one: administrators and moderators, always — they are the accounts that can bar
somebody, change a role or hand over the platform, and a password is one thing somebody
knows. Anybody else may have one if they want it; the gate that *requires* it is narrow on
purpose, because a requirement imposed on buyers is a requirement they route around by not
registering.

Three rules carry most of the weight here.

**An enrolment is not finished until a code has been typed.** A secret written down on our
side and never reaching a telephone would be an account locked behind an authenticator that
does not exist.

**A code is spent.** It is valid for its thirty-second step and the drift either side, so
without remembering the step, a code read over somebody's shoulder works a second time.

**A recovery code is one use and then a row that says so.** Deleting it would make a spent
code indistinguishable from one that was never issued.
"""

import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import ConflictError, PermissionDeniedError
from app.core.security import hash_token
from app.core.totp import generate_secret, matching_step, provisioning_uri
from app.core.vault import lock, unlock
from app.models import TotpCredential, TotpRecoveryCode, User, UserRole
from app.repositories import totp as repo

# Ten, shown once. Enough that somebody can lose a few and still get in, few enough that the
# list is something a person actually keeps rather than a page they close.
RECOVERY_CODES = 10
RECOVERY_CODE_BYTES = 5

# Who cannot sign in without one. Not a setting: it follows from what these accounts can do.
REQUIRED_OF = (UserRole.ADMIN, UserRole.MODERATOR)


class AlreadyEnrolled(ConflictError):
    code = "totp_already_enrolled"


class NotEnrolled(ConflictError):
    code = "totp_not_enrolled"


class WrongCode(PermissionDeniedError):
    """One message for a wrong code, an expired one and a spent one.

    Telling them apart would tell somebody guessing which of their attempts was close.
    """

    code = "totp_invalid_code"


@dataclass(frozen=True)
class Enrolment:
    """What the setup screen shows once and never again."""

    secret: str
    uri: str


@dataclass(frozen=True)
class Confirmed:
    recovery_codes: list[str]


def required_of(user: User) -> bool:
    return user.role in REQUIRED_OF


async def in_force(session: AsyncSession, user: User) -> bool:
    return await repo.is_in_force(session, user.id)


async def begin(session: AsyncSession, settings: Settings, user: User) -> Enrolment:
    """A fresh secret for an account that has none, or has not finished enrolling.

    An unfinished enrolment is replaced rather than resumed: somebody who comes back to this
    screen has almost certainly lost the half-scanned code, and offering them the old secret
    would be offering them the one thing they cannot use.
    """
    existing = await repo.credential_of(session, user.id)
    if existing is not None and existing.confirmed_at is not None:
        raise AlreadyEnrolled("Второй фактор уже включён. Сначала выключите старый.")
    if existing is not None:
        await repo.forget(session, user.id)
    secret = generate_secret()
    await repo.put(
        session,
        TotpCredential(user_id=user.id, secret_encrypted=lock(settings, secret)),
    )
    return Enrolment(
        secret=secret, uri=provisioning_uri(secret, user.email, settings.mail_from_name)
    )


async def confirm(session: AsyncSession, settings: Settings, user: User, code: str) -> Confirmed:
    """Finishes the enrolment, and hands over the way back in without a telephone."""
    credential = await repo.credential_of(session, user.id)
    if credential is None:
        raise NotEnrolled("Сначала начните привязку приложения")
    if credential.confirmed_at is not None:
        raise AlreadyEnrolled("Второй фактор уже включён")
    _spend_step(settings, credential, code)
    credential.confirmed_at = datetime.now(UTC)
    codes = [_recovery_code() for _ in range(RECOVERY_CODES)]
    await repo.add_recovery_codes(
        session,
        [TotpRecoveryCode(user_id=user.id, code_hash=hash_token(one)) for one in codes],
    )
    return Confirmed(recovery_codes=codes)


async def answer(session: AsyncSession, settings: Settings, user_id: uuid.UUID, code: str) -> bool:
    """Checks what somebody typed at sign-in. Says whether it was a recovery code.

    Tries the authenticator first and the recovery list second — the ordinary case should not
    cost a database write, and a six-digit code is never a recovery code anyway.
    """
    credential = await repo.credential_of(session, user_id)
    if credential is None or credential.confirmed_at is None:
        raise NotEnrolled("У этого аккаунта нет второго фактора")
    try:
        _spend_step(settings, credential, code)
    except WrongCode:
        await _spend_recovery_code(session, user_id, code)
        return True
    return False


async def disable(session: AsyncSession, settings: Settings, user: User, code: str) -> None:
    """Removing it asks for a current code, on top of the step-up the route already demands.

    An unattended screen is enough to reach this; it must not be enough to take the second
    factor off, which is the one change that makes every future sign-in easier for whoever is
    sitting there.
    """
    credential = await repo.credential_of(session, user.id)
    if credential is None or credential.confirmed_at is None:
        raise NotEnrolled("Второй фактор не включён")
    _spend_step(settings, credential, code)
    await repo.forget(session, user.id)


async def revoke(session: AsyncSession, user_id: uuid.UUID) -> bool:
    """Takes it away without asking for a code. Says whether there was one.

    For break-glass only — `scripts/grant_role` and the administrator bootstrap. Somebody who
    holds the server can already replace the password; leaving them unable to clear a second
    factor would mean an administrator who loses their telephone and their recovery codes
    locks the platform's only administrator seat for good.
    """
    if await repo.credential_of(session, user_id) is None:
        return False
    await repo.forget(session, user_id)
    return True


def _spend_step(settings: Settings, credential: TotpCredential, code: str) -> None:
    secret = unlock(settings, credential.secret_encrypted)
    if secret is None:
        # the key changed or the row was altered; either way this factor cannot be used again
        raise WrongCode("Код не подходит")
    step = matching_step(secret, code, _now(), after=credential.last_used_step)
    if step is None:
        raise WrongCode("Код не подходит")
    credential.last_used_step = step


async def _spend_recovery_code(session: AsyncSession, user_id: uuid.UUID, code: str) -> None:
    found = await repo.unused_recovery_code(session, user_id, hash_token(_normalised(code)))
    if found is None:
        raise WrongCode("Код не подходит")
    found.used_at = datetime.now(UTC)


def _recovery_code() -> str:
    """Grouped with a dash because these get copied by hand off a screen."""
    raw = secrets.token_hex(RECOVERY_CODE_BYTES)
    return f"{raw[:5]}-{raw[5:]}"


def _normalised(code: str) -> str:
    """Typed back in, a recovery code arrives with whatever spacing and case its owner used."""
    return code.strip().lower().replace(" ", "")


def _now() -> float:
    return datetime.now(UTC).timestamp()
