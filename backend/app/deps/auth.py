import secrets
import uuid
from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.client_ip import client_ip
from app.core.config import Settings
from app.core.cookies import set_session_cookies
from app.core.errors import (
    AppError,
    AuthenticationError,
    EmailNotVerifiedError,
    PasswordChangeRequiredError,
    PermissionDeniedError,
    SecondFactorSetupRequiredError,
    VerificationRequiredError,
)
from app.core.security import csrf_token_for
from app.db.session import get_session
from app.deps.settings import settings_dep
from app.models import Session, User, UserRole
from app.repositories import users as users_repo
from app.services import audit, notifications, totp
from app.services import auth as auth_service
from app.services import sessions as session_service

SessionDep = Annotated[AsyncSession, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(settings_dep)]


async def get_session_row(
    request: Request, response: Response, settings: SettingsDep, db: SessionDep
) -> Session:
    """The session this request belongs to, renewed along the way if it was due.

    The renewal rewrites the cookie on whatever response this request produces, which is why
    the dependency asks for one. It is the only place that can: there is no moment later on
    where the handler knows a token changed underneath it.
    """
    token = request.cookies.get(settings.session_cookie)
    if not token:
        raise AuthenticationError("Требуется вход")
    outcome = await session_service.touch(db, settings, token, ip=client_ip(request, settings))
    if isinstance(outcome, session_service.Replayed):
        # Written with no actor: the token was presented by a party the platform cannot name,
        # and putting the owner in that column would say they did it. The entity is the
        # account it happened to, which is who an administrator would be looking for.
        await audit.record(
            db, None, "session.replayed", "user", outcome.user_id, device=str(outcome.family_id)
        )
        owner = await users_repo.get_by_id(db, outcome.user_id)
        # `touch` has revoked the family; committing it is this line's job and nobody else's.
        # The route never runs, so the commit it would have done never happens — which is
        # exactly how the old refresh rotation threw its own answer to a theft away.
        await db.commit()
        if owner is not None:
            # The one place that could not write to anybody before the queue existed: a
            # dependency has no `BackgroundTasks`, so this letter simply could not be sent.
            # Queued after the commit, like every other — a letter about a revocation that
            # was rolled back would be a lie.
            notifications.deliver(
                settings, notifications.replayed_token_letter(settings, owner.email)
            )
        raise session_service.InvalidSessionError("Сессия недействительна, войдите заново")
    if outcome.wrote:
        # Committed here because nobody else will. Most requests are reads that commit
        # nothing, and everything `touch` writes used to be rolled back with them — which
        # turned a renewal into a sign-out: the browser took the new token and the row it
        # named was never saved. The throttle inside `_slide` keeps this to one commit a
        # minute per session.
        await db.commit()
    if outcome.moved_to is not None:
        owner = await users_repo.get_by_id(db, outcome.session.user_id)
        if owner is not None:
            notifications.deliver(
                settings,
                notifications.session_moved_letter(
                    settings, owner.email, outcome.moved_to.country, outcome.moved_to.asn
                ),
            )
    if outcome.renewed is not None:
        set_session_cookies(response, settings, outcome.renewed)
    return outcome.session


CurrentSession = Annotated[Session, Depends(get_session_row)]


async def get_signed_in_user(row: CurrentSession, db: SessionDep) -> User:
    """Who is signed in, without asking whether the password is theirs.

    The account is re-read even though the session names it: blocking somebody has to take
    effect on their next request, not whenever their session happens to end.
    """
    return await auth_service.get_active_user(db, row.user_id)


async def get_user_owing_a_second_factor(
    user: Annotated[User, Depends(get_signed_in_user)],
) -> User:
    """Past the password gate and not yet past the second-factor one.

    Exists so that the two gates are ordered rather than alternatives. An administrator
    holding a password somebody else chose should replace it first and enrol second; a tier
    that skipped both would have let them enrol with a password that is not theirs.
    """
    if user.must_change_password:
        raise PasswordChangeRequiredError("Сначала задайте свой пароль")
    return user


async def get_current_user(
    user: Annotated[User, Depends(get_user_owing_a_second_factor)], db: SessionDep
) -> User:
    """The ordinary door, and the one a route gets by saying nothing.

    An account whose password was handed to it by somebody else gets no further than the
    screen that replaces it. The rule used to be a list of paths matched by suffix, which
    went wrong in both directions: a new route ending in `/users/me` was let through without
    anybody deciding that, and the list said `/auth/logout`, which never passed this way at
    all. Now a route opts out by asking for `SignedInUser` instead — so a route that says
    nothing is closed, and the mistake somebody makes is a locked door rather than an open one.

    A moderator or an administrator with no second factor gets no further than the screen
    that sets one up. The lookup is one indexed row and is only made for those two roles, so
    the ordinary request of an ordinary account pays nothing for it.
    """
    if totp.required_of(user) and not await totp.in_force(db, user):
        raise SecondFactorSetupRequiredError("Настройте вход по коду, чтобы продолжить")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]

# Signed in, past the password gate, and allowed to go on owing a second factor. Exactly the
# routes that set one up — anything wider would be a way around the gate rather than through it.
UserSettingUpTotp = Annotated[User, Depends(get_user_owing_a_second_factor)]

# Signed in, and deliberately not asked whether the password is their own. Exactly two routes
# want this: the change itself, and the "who am I" the client asks to find out it owes one.
SignedInUser = Annotated[User, Depends(get_signed_in_user)]


async def get_optional_user(request: Request, settings: SettingsDep, db: SessionDep) -> User | None:
    """Whoever is signed in, or nobody.

    Public routes need this for two unrelated reasons. A guest may file a complaint —
    somebody who has just been cheated is not going to register first. And a signed-in buyer
    may have been barred from one particular shop, which the catalogue filter has to know
    about. Neither case may fail: a barred or missing account browses as a guest does.

    Nothing here renews a token or revokes a family. A catalogue page is the wrong place to
    discover a theft and a worse place to act on one: the reader would be signed out mid-scroll
    by a request they did not make, and the write would ride on a route that never commits.
    """
    token = request.cookies.get(settings.session_cookie)
    if not token:
        return None
    row = await session_service.peek(db, settings, token)
    if row is None:
        return None
    try:
        return await auth_service.get_active_user(db, row.user_id)
    except AppError:
        return None


OptionalUser = Annotated[User | None, Depends(get_optional_user)]


def viewer_id_of(user: User | None) -> uuid.UUID | None:
    """What the public catalogue filter asks for: an identifier, or nobody."""
    return None if user is None else user.id


def require_fresh_verification(row: CurrentSession, settings: SettingsDep) -> None:
    """For the handful of actions an unattended screen must not be enough to take.

    Signing in is a claim that fades. Most of what the platform does is reversible and does
    not need the claim renewed; appointing a moderator, handing over the administrator role
    and handing out somebody's password are not, and a laptop left open in a cafe is exactly
    the circumstance they are worth protecting from.

    Changing your own password or login does not come through here: they ask for the current
    password in the request itself, which is the same proof taken at the same moment and does
    not depend on a clock at all.

    A route dependency rather than a parameter type, because it answers "is this moment
    recent enough" and nothing else. Who may do the thing is a separate question with a
    separate answer, and folding the two together would produce a type that quietly let
    anybody through as long as they had typed their password lately.
    """
    if not session_service.is_freshly_verified(row, settings):
        raise VerificationRequiredError("Подтвердите пароль, чтобы продолжить")


def ensure_verified_email(user: User) -> User:
    """For the one thing the platform does on somebody's behalf in public.

    Opening a shop puts a name, a storefront and a way to be paid in front of strangers, and
    the platform is the one presenting it. An address nobody has answered at is not a way to
    reach the person behind that, so it is the moment the confirmation has to have happened.

    Nothing else asks. Browsing, buying, complaining and even running a shop that already
    exists are untouched: a gate on everything would be a gate people route around by not
    signing up, and the address is not what makes any of those safe.

    A plain function rather than a dependency, so the route composes it *after* the role
    check. As a route-level dependency it ran first, and a buyer reaching for a shop was told
    to confirm their address — an answer about the wrong problem, and one that implies the
    shop was otherwise theirs to open.
    """
    if user.email_verified_at is None:
        raise EmailNotVerifiedError("Подтвердите адрес почты, чтобы открыть магазин")
    return user


def require_role(*roles: UserRole) -> Callable[[User], Awaitable[User]]:
    async def dependency(user: CurrentUser) -> User:
        if user.role not in roles:
            raise PermissionDeniedError("Недостаточно прав для этого действия")
        return user

    return dependency


# What the browser says about where it sent this from. `cross-site` is the one that must
# never reach a mutating route; `same-origin` and `same-site` are ours, and `none` is a user
# typing an address or following a bookmark, which cannot be a forged POST.
HOSTILE_FETCH_SITE = "cross-site"


def require_csrf(request: Request, settings: SettingsDep) -> None:
    """Three questions, cheapest first, and each one catches what the others cannot.

    The token is the old guarantee: a cross-site page cannot read our cookie, so it cannot
    repeat it in a header. `Sec-Fetch-Site` is the browser's own account of where the request
    came from, which a page cannot write. `Origin` is checked against the addresses we expect
    to be called from, for the browsers that do not send the first.

    None of the three is sufficient alone — the fetch metadata is absent in older browsers,
    and `Origin` is absent on some same-origin requests. Together they fail closed.

    What the token no longer has to do alone is survive somebody planting a cookie: the value
    is derived from the session's family rather than drawn at random, so a planted pair
    satisfies the double submit and still fails to be what this device should be carrying.
    That check is in `require_bound_csrf`, which the authorized routes use.
    """
    if request.headers.get("sec-fetch-site") == HOSTILE_FETCH_SITE:
        raise PermissionDeniedError("Запрос пришёл со стороннего сайта")
    _ensure_origin_is_ours(request, settings)
    _ensure_double_submit(request, settings)


def require_bound_csrf(request: Request, settings: SettingsDep, row: CurrentSession) -> None:
    """The same three questions, and then the one only a server can ask.

    Used wherever a session is required anyway. The value in the cookie has to be the value
    this family is supposed to carry — which somebody who can write cookies but cannot sign
    with our key is unable to produce.
    """
    require_csrf(request, settings)
    expected = csrf_token_for(settings, row.family_id)
    presented = request.headers.get(settings.csrf_header_name) or ""
    if not secrets.compare_digest(presented, expected):
        raise PermissionDeniedError("CSRF-токен не совпадает")


def _ensure_double_submit(request: Request, settings: Settings) -> None:
    cookie_token = request.cookies.get(settings.csrf_cookie)
    header_token = request.headers.get(settings.csrf_header_name)
    if not cookie_token or not header_token:
        raise PermissionDeniedError("Отсутствует CSRF-токен")
    if not secrets.compare_digest(cookie_token, header_token):
        raise PermissionDeniedError("CSRF-токен не совпадает")


def _ensure_origin_is_ours(request: Request, settings: Settings) -> None:
    """An absent `Origin` is not an offence: browsers omit it on same-origin GETs and on some
    form posts, and a server-to-server caller has none to send. A present one that we do not
    recognise is, and nothing configured to recognise means the question is not asked."""
    origin = request.headers.get("origin")
    expected = settings.trusted_origins
    if origin is None or not expected:
        return
    if origin not in expected:
        raise PermissionDeniedError("Запрос пришёл со стороннего сайта")
