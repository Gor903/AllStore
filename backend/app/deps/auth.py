import secrets
import uuid
from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import AppError, AuthenticationError, PermissionDeniedError
from app.core.tokens import InvalidAccessToken, decode_access_token
from app.db.session import get_session
from app.deps.settings import settings_dep
from app.models import User, UserRole
from app.services import auth as auth_service

SessionDep = Annotated[AsyncSession, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(settings_dep)]


async def get_current_user(request: Request, settings: SettingsDep, session: SessionDep) -> User:
    token = request.cookies.get(settings.access_cookie_name)
    if not token:
        raise AuthenticationError("Требуется вход")
    try:
        payload = decode_access_token(settings, token)
    except InvalidAccessToken as exc:
        raise AuthenticationError("Сессия недействительна, войдите заново") from exc
    # the status is re-read on every request: blocking an account must take effect at once
    return await auth_service.get_active_user(session, payload.user_id)


CurrentUser = Annotated[User, Depends(get_current_user)]


async def get_optional_user(
    request: Request, settings: SettingsDep, session: SessionDep
) -> User | None:
    """Whoever is signed in, or nobody.

    Public routes need this for two unrelated reasons. A guest may file a complaint —
    somebody who has just been cheated is not going to register first. And a signed-in buyer
    may have been barred from one particular shop, which the catalogue filter has to know
    about. Neither case may fail: a barred or missing account browses as a guest does.
    """
    token = request.cookies.get(settings.access_cookie_name)
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


def require_csrf(request: Request, settings: SettingsDep) -> None:
    """Double submit: the header must repeat the cookie a cross-site page cannot read."""
    cookie_token = request.cookies.get(settings.csrf_cookie_name)
    header_token = request.headers.get(settings.csrf_header_name)
    if not cookie_token or not header_token:
        raise PermissionDeniedError("Отсутствует CSRF-токен")
    if not secrets.compare_digest(cookie_token, header_token):
        raise PermissionDeniedError("CSRF-токен не совпадает")
