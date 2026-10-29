import uuid
from datetime import UTC, datetime, timedelta
from functools import lru_cache

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import (
    AccountNotActiveError,
    AuthenticationError,
    BreachedPasswordError,
    ConflictError,
    NoPasswordSetError,
)
from app.core.mail import Letter
from app.core.security import (
    generate_token,
    hash_password,
    hash_password_in_thread,
    hash_token,
    normalise,
    password_needs_rehash,
    verify_password_in_thread,
)
from app.models import Business, PasswordResetToken, User, UserRole, UserStatus
from app.repositories import auth_tokens, users
from app.repositories import sessions as sessions_repo
from app.schemas.auth import BuyerRegisterRequest, SellerRegisterRequest
from app.services import breached_passwords, notifications
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


class AddressAlreadyTaken(Exception):
    """Raised inwards, never outwards.

    The caller turns this into the same answer a successful registration gets — see
    `api/auth.py`. It exists so the API can tell the two apart well enough to write to the
    right person, and for no other reason.
    """


async def ensure_password_is_still_a_secret(settings: Settings, password: str) -> None:
    """Refuses a password that is already on a list attackers try first.

    Composition rules were considered and left out: they produce `Password1!` and a note on a
    monitor. What a password needs is not to be one somebody has already seen — see
    services/breached_passwords.py, which answers that without the password leaving.
    """
    if await breached_passwords.is_known_leaked(settings, normalise(password)):
        raise BreachedPasswordError(
            "Этот пароль уже встречался в утечках и больше не секрет — выберите другой"
        )


async def register_buyer(session: AsyncSession, data: BuyerRegisterRequest) -> User:
    """Inserts, and lets the unique index be the one that decides.

    Looking first and inserting afterwards is two statements with a gap between them, and two
    registrations for the same address can both pass the look. The index cannot be raced; the
    check could only ever have been a nicer error message, and it is not even that any more —
    the answer is the same either way.
    """
    user = User(
        email=data.normalized_email,
        phone=data.phone,
        password_hash=await hash_password_in_thread(data.password.get_secret_value()),
        role=UserRole.BUYER,
    )
    return await _insert(session, user)


async def _insert(session: AsyncSession, user: User) -> User:
    """A savepoint, because a failed insert poisons the transaction it happened in.

    Without one the caller could not go on to write anything else — and it has a letter to
    send and, on the seller path, a business to create.
    """
    try:
        async with session.begin_nested():
            return await users.add(session, user)
    except IntegrityError as taken:
        raise AddressAlreadyTaken from taken


async def register_seller(
    session: AsyncSession, data: SellerRegisterRequest
) -> tuple[User, Business]:
    user = await _insert(
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
    """For the administrator's own panel, where saying so plainly is the right answer.

    Registration deliberately does not use this. A public form that refuses a taken address
    out loud is a form anybody can walk a list of addresses through to learn who has an
    account here; an administrator looking at their own list of moderators is not that, and
    an address they cannot see the state of is an address they cannot act on.
    """
    if await users.email_exists(session, email):
        raise ConflictError("Пользователь с таким email уже зарегистрирован")
    if phone is not None and await users.phone_exists(session, phone):
        raise ConflictError("Пользователь с таким телефоном уже зарегистрирован")


async def authenticate(session: AsyncSession, email: str, password: str) -> User:
    user = await users.get_by_email(session, email.strip().lower())
    if user is None or user.password_hash is None:
        # An account with no password is one that signs in with a provider. It gets the same
        # answer and the same cost as an address nobody has: saying "that one has no password"
        # would tell a stranger how this person signs in.
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


async def request_password_reset(
    session: AsyncSession, settings: Settings, email: str
) -> Letter | None:
    """Builds the letter; does not send it. Returns None when there is nobody to write to.

    Sending belongs to the caller, after the commit and after the answer. Waiting on somebody
    else's mail server inside the request would make the response slower for an address that
    exists than for one that does not — which is the question this endpoint's identical
    wording exists to avoid answering.
    """
    user = await users.get_by_email(session, email.strip().lower())
    if user is None or user.status is not UserStatus.ACTIVE:
        return None
    raw_token = generate_token()
    await auth_tokens.add_password_reset_token(
        session,
        PasswordResetToken(
            user_id=user.id,
            token_hash=hash_token(raw_token),
            expires_at=datetime.now(UTC) + timedelta(hours=settings.password_reset_ttl_hours),
        ),
    )
    return notifications.password_reset_letter(settings, user.email, raw_token)


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
    if not await verify_password_in_thread(current_password, password_of(user)):
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
    if not await verify_password_in_thread(current_password, password_of(user)):
        raise InvalidCredentialsError("Текущий пароль неверен")
    user.password_hash = await hash_password_in_thread(new_password)
    user.must_change_password = False
    # same rule as a reset: a password change ends every session, this one included
    await sessions_repo.revoke_all_for_user(session, user.id, CREDENTIALS_CHANGED)


def password_of(user: User) -> str:
    """The stored hash, or a refusal that says what to do instead.

    An account opened with Google has no password and never had one. Asking it to prove one
    is a dead end unless the answer points somewhere: the reset flow, which works for exactly
    these accounts because the provider already confirmed the address.
    """
    if user.password_hash is None:
        raise NoPasswordSetError(
            "У этого аккаунта нет пароля — он входит через Google. "
            "Чтобы задать пароль, воспользуйтесь восстановлением."
        )
    return user.password_hash


async def verify_password_of(user: User, password: str) -> None:
    """Shared by every place that asks somebody to prove the password they already gave.

    One function so the refusal is worded identically wherever it comes from — a message that
    differs by route is a message that says which route you reached.
    """
    if not await verify_password_in_thread(password, password_of(user)):
        raise InvalidCredentialsError("Текущий пароль неверен")


async def get_active_user(session: AsyncSession, user_id: uuid.UUID) -> User:
    user = await users.get_by_id(session, user_id)
    if user is None:
        raise InvalidCredentialsError("Сессия недействительна, войдите заново")
    _ensure_active(user)
    return user
