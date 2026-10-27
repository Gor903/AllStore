"""Personal invitations to the moderator role: the only way the role is handed out.

A moderator judges other people's shops and bars other people's accounts, so the role is not
something a form on the public site can grant. It is addressed to one person, by name, by an
administrator, and the link that carries it works once.

What the table keeps, and why each part is there:

* only the sha256 of the secret. A database leak yields nothing anyone can present;
* the address it was issued for, checked again at registration. A link forwarded to somebody
  else is a link that stops working;
* an expiry, a revocation and a use, each with its own timestamp. "Pending" is derived from
  them rather than stored, so there is no status column to fall out of step;
* a single statement to spend it. Two people clicking the same link in the same second is the
  race this exists to lose gracefully — see `repositories/invitations.claim`.
"""

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import ConflictError, NotFoundError, ValidationFailedError
from app.core.security import generate_token, hash_password, hash_token
from app.models import InvitationStatus, ModeratorInvitation, User, UserRole
from app.repositories import invitations as invitations_repo
from app.repositories import users as users_repo
from app.services import audit, auth
from app.services.notifications import send_moderator_invitation_email

ENTITY = "moderator_invitation"


class InvitationNotFoundError(NotFoundError):
    code = "invitation_not_found"


class InvitationAlreadyOpenError(ConflictError):
    code = "invitation_already_open"


class InvitationNotPendingError(ConflictError):
    code = "invitation_not_pending"


class InvalidInvitationError(ValidationFailedError):
    """Wrong token, wrong address, expired, revoked, already used — one answer for all of them.

    Telling them apart would turn the form into an oracle: which addresses were invited, which
    links have been spent, which are merely stale. None of that is the caller's to learn.
    """

    code = "invalid_invitation"


class AccountExistsError(ConflictError):
    code = "account_exists"


async def create(
    session: AsyncSession, admin: User, settings: Settings, email: str
) -> tuple[ModeratorInvitation, str]:
    """Returns the invitation and its secret. The secret is never readable again — not from
    the database, not from this API — so the caller shows it once or sends it once."""
    normalized = email.strip().lower()
    if await users_repo.email_exists(session, normalized):
        raise AccountExistsError(
            "На этот адрес уже зарегистрирован аккаунт: роль ему меняют на экране пользователей"
        )
    if await invitations_repo.get_live_for(session, normalized) is not None:
        raise InvitationAlreadyOpenError(
            "Для этого адреса уже есть действующее приглашение — отзовите его, чтобы выдать новое"
        )

    raw_token = generate_token()
    invitation = await invitations_repo.add(
        session,
        ModeratorInvitation(
            email=normalized,
            token_hash=hash_token(raw_token),
            created_by_user_id=admin.id,
            expires_at=datetime.now(UTC) + timedelta(hours=settings.moderator_invitation_ttl_hours),
        ),
    )
    await audit.record(session, admin, "moderator.invited", ENTITY, invitation.id, email=normalized)
    await send_moderator_invitation_email(normalized, raw_token)
    return invitation, raw_token


async def revoke(
    session: AsyncSession, admin: User, invitation_id: uuid.UUID
) -> ModeratorInvitation:
    invitation = await invitations_repo.get(session, invitation_id)
    if invitation is None:
        raise InvitationNotFoundError("Приглашение не найдено")
    if invitation.status is not InvitationStatus.PENDING:
        # an expired one needs no revoking and an accepted one cannot be taken back this way:
        # that is a role change, on the users screen
        raise InvitationNotPendingError("Отозвать можно только действующее приглашение")

    invitation.revoked_at = datetime.now(UTC)
    invitation.revoked_by_user_id = admin.id
    await session.flush()
    await audit.record(
        session, admin, "moderator.invite_revoked", ENTITY, invitation.id, email=invitation.email
    )
    return invitation


async def accept(session: AsyncSession, token: str, email: str, password: str) -> User:
    """Spends the invitation and creates the moderator, in one transaction.

    The order matters. The invitation is claimed first, so that if two requests arrive with
    the same link only one of them ever reaches the account creation; a check-then-create
    would let both through and leave the second to fail on the email index, which is a
    different and much less obvious error.
    """
    normalized = email.strip().lower()
    invitation = await invitations_repo.claim(session, hash_token(token), datetime.now(UTC))
    if invitation is None or invitation.email != normalized:
        raise InvalidInvitationError("Приглашение недействительно или устарело")

    await auth.ensure_identifiers_free(session, normalized, None)
    user = await users_repo.add(
        session,
        User(
            email=normalized,
            password_hash=hash_password(password),
            role=UserRole.MODERATOR,
        ),
    )
    invitation.accepted_user_id = user.id
    await session.flush()
    await audit.record(
        session, user, "moderator.invite_accepted", ENTITY, invitation.id, email=normalized
    )
    return user


async def list_all(
    session: AsyncSession, limit: int, offset: int
) -> tuple[Sequence[ModeratorInvitation], int]:
    return await invitations_repo.list_all(session, limit, offset)
