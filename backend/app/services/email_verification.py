"""Confirming that an address belongs to the person who typed it.

Two things use this and they are the same thing. An account confirms the address it registered
with; an account that wants a different one confirms that one instead. The only difference is
whether the address in the row matches the account's own.

**The old address keeps working until the new one answers.** Changing the login used to take
effect the moment the form was submitted, which meant a typo in the new address locked the
owner out of their own account with no way back — the password was right, and the login was a
place nobody could read. Now nothing moves until somebody opens a letter at the new address.

**Nothing says whether the address was free.** Asking to move to an address that already has
an account gets the same answer as asking to move to a free one; the letter simply goes to
whoever owns it, saying somebody tried. Refusing out loud would make this form a way of asking
whether a particular person has an account here.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import ConflictError
from app.core.mail import Letter
from app.core.security import generate_token, hash_token
from app.models import EmailVerification, User
from app.repositories import email_verifications as repo
from app.repositories import users
from app.services import notifications, sessions


class InvalidVerificationTokenError(ConflictError):
    code = "invalid_verification_token"


class AddressUnchangedError(ConflictError):
    """Asked to move to the address it already has.

    Refused rather than quietly accepted for the same reason as before: answering "check your
    email" to a request that changes nothing sends somebody to wait for a letter about an
    address they are already using.
    """

    code = "same_email"


@dataclass(frozen=True)
class Requested:
    """What the caller has to send, and where. Two letters when an address is being left
    behind: one asking the new address to confirm, one telling the old address it happened."""

    confirm: Letter
    notice: Letter | None = None


async def request(session: AsyncSession, settings: Settings, user: User, address: str) -> Requested:
    """Builds the letters; sending belongs to the caller, after the commit."""
    normalized = address.strip().lower()
    await repo.supersede_all(session, user.id)
    token = generate_token()
    await repo.add(
        session,
        EmailVerification(
            user_id=user.id,
            token_hash=hash_token(token),
            email=normalized,
            expires_at=datetime.now(UTC) + timedelta(hours=settings.email_verification_ttl_hours),
        ),
    )
    moving = normalized != user.email
    return Requested(
        confirm=notifications.email_confirmation_letter(settings, normalized, token, moving=moving),
        notice=notifications.email_change_notice_letter(settings, user.email, normalized)
        if moving
        else None,
    )


@dataclass(frozen=True)
class Confirmed:
    user: User
    # True only when the account actually changed address, which is the case that ends
    # sessions. Confirming the address you registered with must not sign you out of the
    # browser you were asked to confirm it from.
    moved: bool


async def confirm(session: AsyncSession, raw_token: str) -> Confirmed:
    """Spends the link and makes the address the account's own.

    The address is checked for being free here rather than when the letter was asked for: in
    between, somebody else may have registered it. The unique index is what actually decides,
    and this check exists only so the answer is a sentence rather than a constraint violation.
    """
    row = await repo.get_by_hash(session, hash_token(raw_token))
    now = datetime.now(UTC)
    if row is None or row.used_at is not None or row.expires_at <= now:
        raise InvalidVerificationTokenError("Ссылка недействительна или устарела")
    user = await users.get_by_id(session, row.user_id)
    if user is None:
        raise InvalidVerificationTokenError("Ссылка недействительна или устарела")

    await repo.spend(session, row)
    moved = row.email != user.email
    if moved:
        await _move(session, user, row.email)
    user.email_verified_at = now
    await session.flush()
    return Confirmed(user=user, moved=moved)


async def _move(session: AsyncSession, user: User, address: str) -> None:
    if await users.email_exists(session, address):
        raise InvalidVerificationTokenError("Этот адрес уже занят другим аккаунтом")
    user.email = address
    # half the credentials changed, so the sessions holding the other half end with it
    await sessions.sign_out_everywhere(session, user.id, sessions.CREDENTIALS_CHANGED)


def pending_address(row: EmailVerification | None, user: User) -> str | None:
    """The address this account is waiting to move to, or nothing.

    A live row naming the account's own address is somebody confirming what they already have,
    which is not a move and has nothing to show.
    """
    if row is None or row.email == user.email:
        return None
    return row.email
