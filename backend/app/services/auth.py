import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import lru_cache

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import AuthenticationError, ConflictError, PermissionDeniedError
from app.core.security import (
    generate_token,
    hash_password,
    hash_password_in_thread,
    hash_token,
    password_needs_rehash,
    verify_password_in_thread,
)
from app.core.tokens import create_access_token
from app.models import Business, PasswordResetToken, RefreshToken, User, UserRole, UserStatus
from app.repositories import auth_tokens, users
from app.schemas.auth import BuyerRegisterRequest, SellerRegisterRequest
from app.services.notifications import send_password_reset_email


class InvalidCredentialsError(AuthenticationError):
    code = "invalid_credentials"


class InvalidRefreshTokenError(AuthenticationError):
    code = "invalid_refresh_token"


class InvalidResetTokenError(AuthenticationError):
    code = "invalid_reset_token"


class SameEmailError(ConflictError):
    """Asked to change the login to the one it already is.

    Refused rather than quietly accepted, because "accepted" here means ending every session
    and reporting a change that did not happen — which is exactly how somebody who came to
    change their password ends up logged out, confused, and with nothing altered.
    """

    code = "same_email"


class AccountNotActiveError(PermissionDeniedError):
    code = "account_not_active"


@dataclass(frozen=True)
class IssuedTokens:
    access_token: str
    refresh_token: str
    csrf_token: str


@dataclass(frozen=True)
class Rotated:
    """The session continued: the caller holds a new token and the old one is retired."""

    user: User
    tokens: IssuedTokens


@dataclass(frozen=True)
class ReuseDetected:
    """An already rotated token came back, so every session of that account was revoked.

    Returned rather than raised, and that is the whole reason this function answers with a
    value instead of simply throwing. Revoking the family is a write, the commit belongs to
    the endpoint, and an exception unwinds the session before the endpoint can reach it —
    which left the platform refusing the replay and keeping the stolen family alive. The
    refusal is still the endpoint's to raise, in the same words as every other one: a replay
    must not be able to tell itself apart from a token that never existed.
    """


@lru_cache
def _dummy_hash() -> str:
    """Verified against when the email is unknown, so timing does not reveal existing accounts."""
    return hash_password("dummy-password-for-timing")


async def register_buyer(session: AsyncSession, data: BuyerRegisterRequest) -> User:
    await ensure_identifiers_free(session, data.normalized_email, data.phone)
    user = User(
        email=data.normalized_email,
        phone=data.phone,
        password_hash=await hash_password_in_thread(data.password.get_secret_value()),
        role=UserRole.BUYER,
    )
    return await users.add(session, user)


async def register_seller(
    session: AsyncSession, data: SellerRegisterRequest
) -> tuple[User, Business]:
    await ensure_identifiers_free(session, data.normalized_email, data.phone)
    user = await users.add(
        session,
        User(
            email=data.normalized_email,
            phone=data.phone,
            password_hash=await hash_password_in_thread(data.password.get_secret_value()),
            role=UserRole.SELLER,
        ),
    )
    # the business waits for a moderator: registration alone does not open a storefront
    business = await users.add_business(
        session,
        Business(owner_user_id=user.id, legal_name=data.legal_name, display_name=data.display_name),
    )
    return user, business


async def ensure_identifiers_free(session: AsyncSession, email: str, phone: str | None) -> None:
    """Public: appointing a moderator goes through its own service rather than this module,
    and the two must refuse a taken address in the same words."""
    if await users.email_exists(session, email):
        raise ConflictError("Пользователь с таким email уже зарегистрирован")
    if phone is not None and await users.phone_exists(session, phone):
        raise ConflictError("Пользователь с таким телефоном уже зарегистрирован")


async def authenticate(session: AsyncSession, email: str, password: str) -> User:
    user = await users.get_by_email(session, email.strip().lower())
    if user is None:
        await verify_password_in_thread(password, _dummy_hash())
        raise InvalidCredentialsError("Неверный email или пароль")
    if not await verify_password_in_thread(password, user.password_hash):
        raise InvalidCredentialsError("Неверный email или пароль")
    if password_needs_rehash(user.password_hash):
        user.password_hash = await hash_password_in_thread(password)
    _ensure_active(user)
    # after the status check: a refused attempt is not a login, however correct the password
    user.last_login_at = datetime.now(UTC)
    await session.flush()
    return user


def _ensure_active(user: User) -> None:
    if user.status is not UserStatus.ACTIVE:
        raise AccountNotActiveError("Доступ к аккаунту ограничен, обратитесь в поддержку")


async def issue_tokens(
    session: AsyncSession, settings: Settings, user: User, user_agent: str | None = None
) -> IssuedTokens:
    raw_refresh = generate_token()
    await auth_tokens.add_refresh_token(
        session,
        RefreshToken(
            user_id=user.id,
            token_hash=hash_token(raw_refresh),
            expires_at=datetime.now(UTC) + timedelta(days=settings.refresh_token_ttl_days),
            user_agent=user_agent[:255] if user_agent else None,
        ),
    )
    return IssuedTokens(
        access_token=create_access_token(settings, user.id, user.role.value),
        refresh_token=raw_refresh,
        csrf_token=generate_token(),
    )


async def rotate_refresh_token(
    session: AsyncSession, settings: Settings, raw_refresh: str, user_agent: str | None = None
) -> Rotated | ReuseDetected:
    stored = await auth_tokens.get_refresh_token(session, hash_token(raw_refresh))
    if stored is None:
        raise InvalidRefreshTokenError("Сессия недействительна, войдите заново")
    if stored.revoked_at is not None:
        # the token was already rotated: someone is replaying a stolen copy
        await auth_tokens.revoke_all_for_user(session, stored.user_id)
        return ReuseDetected()
    if stored.expires_at <= datetime.now(UTC):
        raise InvalidRefreshTokenError("Сессия истекла, войдите заново")

    user = await users.get_by_id(session, stored.user_id)
    if user is None:
        raise InvalidRefreshTokenError("Сессия недействительна, войдите заново")
    _ensure_active(user)

    issued = await issue_tokens(session, settings, user, user_agent)
    replacement = await auth_tokens.get_refresh_token(session, hash_token(issued.refresh_token))
    await auth_tokens.revoke_refresh_token(
        session, stored, replaced_by_id=replacement.id if replacement else None
    )
    return Rotated(user=user, tokens=issued)


async def revoke_refresh_token(session: AsyncSession, raw_refresh: str) -> None:
    stored = await auth_tokens.get_refresh_token(session, hash_token(raw_refresh))
    if stored is not None and stored.revoked_at is None:
        await auth_tokens.revoke_refresh_token(session, stored)


async def request_password_reset(session: AsyncSession, settings: Settings, email: str) -> None:
    """Always succeeds from the caller's side — the response must not reveal known addresses."""
    user = await users.get_by_email(session, email.strip().lower())
    if user is None or user.status is not UserStatus.ACTIVE:
        return
    raw_token = generate_token()
    await auth_tokens.add_password_reset_token(
        session,
        PasswordResetToken(
            user_id=user.id,
            token_hash=hash_token(raw_token),
            expires_at=datetime.now(UTC) + timedelta(hours=settings.password_reset_ttl_hours),
        ),
    )
    await send_password_reset_email(user.email, raw_token)


async def reset_password(session: AsyncSession, raw_token: str, new_password: str) -> User:
    stored = await auth_tokens.get_password_reset_token(session, hash_token(raw_token))
    if stored is None or stored.used_at is not None or stored.expires_at <= datetime.now(UTC):
        raise InvalidResetTokenError("Ссылка недействительна или устарела")
    user = await users.get_by_id(session, stored.user_id)
    if user is None:
        raise InvalidResetTokenError("Ссылка недействительна или устарела")

    user.password_hash = await hash_password_in_thread(new_password)
    # whatever the old password was, this one they chose themselves
    user.must_change_password = False
    await auth_tokens.mark_password_reset_used(session, stored)
    # a password change ends every session: that is the point of a reset
    await auth_tokens.revoke_all_for_user(session, user.id)
    return user


async def change_email(
    session: AsyncSession, user: User, current_password: str, new_email: str
) -> str:
    """Changing the login is as grave as changing the password, so it is proved the same way.

    Returns the address left behind: the journal records what it was, and after the write
    nobody can tell any more.
    """
    if not await verify_password_in_thread(current_password, user.password_hash):
        raise InvalidCredentialsError("Текущий пароль неверен")
    normalized = new_email.strip().lower()
    if normalized == user.email:
        # answering "changed, sign in again" to a request that changed nothing is worse than
        # a refusal: it ends every session, says something happened, and nothing did
        raise SameEmailError("Это и есть текущий логин — менять нечего")
    await ensure_identifiers_free(session, normalized, None)
    was = user.email
    user.email = normalized
    # an address that was verified is no longer the address that was verified
    user.email_verified_at = None
    # half the credentials changed, so the sessions holding the other half end too
    await auth_tokens.revoke_all_for_user(session, user.id)
    return was


async def change_password(
    session: AsyncSession, user: User, current_password: str, new_password: str
) -> None:
    """A signed-in account replaces its own password, proving it knows the old one.

    The proof matters most in the case this exists for: an administrator whose first password
    came out of a deploy variable. Without it, an unattended session would be enough to take
    the account over permanently.
    """
    if not await verify_password_in_thread(current_password, user.password_hash):
        raise InvalidCredentialsError("Текущий пароль неверен")
    user.password_hash = await hash_password_in_thread(new_password)
    user.must_change_password = False
    # same rule as a reset: a password change ends every session, this one included
    await auth_tokens.revoke_all_for_user(session, user.id)


async def get_active_user(session: AsyncSession, user_id: uuid.UUID) -> User:
    user = await users.get_by_id(session, user_id)
    if user is None:
        raise InvalidCredentialsError("Сессия недействительна, войдите заново")
    _ensure_active(user)
    return user
