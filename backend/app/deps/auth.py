import secrets
import uuid
from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import (
    AppError,
    AuthenticationError,
    PasswordChangeRequiredError,
    PermissionDeniedError,
)
from app.core.tokens import InvalidAccessToken, decode_access_token
from app.db.session import get_session
from app.deps.settings import settings_dep
from app.models import User, UserRole
from app.services import auth as auth_service

SessionDep = Annotated[AsyncSession, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(settings_dep)]


async def get_signed_in_user(request: Request, settings: SettingsDep, session: SessionDep) -> User:
    """Who is signed in, without asking whether the password is theirs."""
    token = request.cookies.get(settings.access_cookie)
    if not token:
        raise AuthenticationError("Требуется вход")
    try:
        payload = decode_access_token(settings, token)
    except InvalidAccessToken as exc:
        raise AuthenticationError("Сессия недействительна, войдите заново") from exc
    # the status is re-read on every request: blocking an account must take effect at once
    return await auth_service.get_active_user(session, payload.user_id)


async def get_current_user(user: Annotated[User, Depends(get_signed_in_user)]) -> User:
    """The ordinary door, and the one a route gets by saying nothing.

    An account whose password was handed to it by somebody else gets no further than the
    screen that replaces it. The rule used to be a list of paths matched by suffix, which
    went wrong in both directions: a new route ending in `/users/me` was let through without
    anybody deciding that, and the list said `/auth/logout`, which never passed this way at
    all. Now a route opts out by asking for `SignedInUser` instead — so a route that says
    nothing is closed, and the mistake somebody makes is a locked door rather than an open one.
    """
    if user.must_change_password:
        raise PasswordChangeRequiredError("Сначала задайте свой пароль")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]

# Signed in, and deliberately not asked whether the password is their own. Exactly two routes
# want this: the change itself, and the "who am I" the client asks to find out it owes one.
SignedInUser = Annotated[User, Depends(get_signed_in_user)]


async def get_optional_user(
    request: Request, settings: SettingsDep, session: SessionDep
) -> User | None:
    """Whoever is signed in, or nobody.

    Public routes need this for two unrelated reasons. A guest may file a complaint —
    somebody who has just been cheated is not going to register first. And a signed-in buyer
    may have been barred from one particular shop, which the catalogue filter has to know
    about. Neither case may fail: a barred or missing account browses as a guest does.
    """
    token = request.cookies.get(settings.access_cookie)
    if not token:
        return None
    try:
        payload = decode_access_token(settings, token)
    except InvalidAccessToken:
        return None
    try:
        return await auth_service.get_active_user(session, payload.user_id)
    except AppError:
        return None


OptionalUser = Annotated[User | None, Depends(get_optional_user)]


def viewer_id_of(user: User | None) -> uuid.UUID | None:
    """What the public catalogue filter asks for: an identifier, or nobody."""
    return None if user is None else user.id


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

    None of the three is sufficient alone — the token says nothing if an attacker can plant a
    cookie, the fetch metadata is absent in older browsers, and `Origin` is absent on some
    same-origin requests. Together they fail closed.
    """
    if request.headers.get("sec-fetch-site") == HOSTILE_FETCH_SITE:
        raise PermissionDeniedError("Запрос пришёл со стороннего сайта")
    _ensure_origin_is_ours(request, settings)

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
