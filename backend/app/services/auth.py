import uuid
from datetime import UTC, datetime, timedelta
from functools import lru_cache

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import AccountNotActiveError, AuthenticationError, ConflictError
from app.core.security import (
    generate_token,
    hash_password,
    hash_password_in_thread,
    hash_token,
    password_needs_rehash,
    verify_password_in_thread,
)
from app.models import Business, PasswordResetToken, User, UserRole, UserStatus
from app.repositories import auth_tokens, users
from app.repositories import sessions as sessions_repo
from app.schemas.auth import BuyerRegisterRequest, SellerRegisterRequest
from app.services.notifications import send_password_reset_email
from app.services.sessions import CREDENTIALS_CHANGED


class InvalidCredentialsError(AuthenticationError):
    code = "invalid_credentials"


class InvalidResetTokenError(AuthenticationError):
    code = "invalid_reset_token"


class SameEmailError(ConflictError):
    """Asked to change the login to the one it already is.

    Refused rather than quietly accepted, because "accepted" here means ending every session
    and reporting a change that did not happen — which is exactly how somebody who came to
    change their password ends up logged out, confused, and with nothing altered.
    """

    code = "same_email"


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
    await sessions_repo.revoke_all_for_user(session, user.id, CREDENTIALS_CHANGED)
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
    await sessions_repo.revoke_all_for_user(session, user.id, CREDENTIALS_CHANGED)
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
    await sessions_repo.revoke_all_for_user(session, user.id, CREDENTIALS_CHANGED)


async def verify_password_of(user: User, password: str) -> None:
    """Shared by every place that asks somebody to prove the password they already gave.

    One function so the refusal is worded identically wherever it comes from — a message that
    differs by route is a message that says which route you reached.
    """
    if not await verify_password_in_thread(password, user.password_hash):
        raise InvalidCredentialsError("Текущий пароль неверен")


async def get_active_user(session: AsyncSession, user_id: uuid.UUID) -> User:
    user = await users.get_by_id(session, user_id)
    if user is None:
        raise InvalidCredentialsError("Сессия недействительна, войдите заново")
    _ensure_active(user)
    return user
