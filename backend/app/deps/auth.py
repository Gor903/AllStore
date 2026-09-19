import secrets
from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import AuthenticationError, PermissionDeniedError
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
