from fastapi import APIRouter, Depends, Request, Response, status

from app.core.cookies import clear_auth_cookies, set_auth_cookies
from app.core.errors import AuthenticationError
from app.deps.auth import CurrentUser, SessionDep, SettingsDep, require_csrf
from app.deps.rate_limit import limit_invitation_attempts
from app.schemas.auth import (
    BuyerRegisterRequest,
    EmailChangeRequest,
    LoginRequest,
    MessageResponse,
    PasswordChangeRequest,
    PasswordResetConfirmRequest,
    PasswordResetRequest,
    SellerRegisterRequest,
    SellerRegisterResponse,
    UserRead,
)
from app.schemas.invitation import ModeratorRegisterRequest
from app.services import audit, invitations
from app.services import auth as auth_service

router = APIRouter(prefix="/auth", tags=["auth"])

# what these entries are about: the account itself, not anything it owns
ENTITY = "user"


@router.post("/register/buyer", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def register_buyer(
    payload: BuyerRegisterRequest,
    response: Response,
    request: Request,
    settings: SettingsDep,
    session: SessionDep,
) -> UserRead:
    user = await auth_service.register_buyer(session, payload)
    tokens = await auth_service.issue_tokens(
        session, settings, user, request.headers.get("user-agent")
    )
    await session.commit()
    set_auth_cookies(response, settings, tokens)
    return UserRead.model_validate(user)


@router.post(
    "/register/seller", response_model=SellerRegisterResponse, status_code=status.HTTP_201_CREATED
)
async def register_seller(
    payload: SellerRegisterRequest,
    response: Response,
    request: Request,
    settings: SettingsDep,
    session: SessionDep,
) -> SellerRegisterResponse:
    user, business = await auth_service.register_seller(session, payload)
    tokens = await auth_service.issue_tokens(
        session, settings, user, request.headers.get("user-agent")
    )
    await session.commit()
    set_auth_cookies(response, settings, tokens)
    return SellerRegisterResponse.model_validate({"user": user, "business": business})


@router.post(
    "/register/moderator",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(limit_invitation_attempts)],
)
async def register_moderator(
    payload: ModeratorRegisterRequest,
    response: Response,
    request: Request,
    settings: SettingsDep,
    session: SessionDep,
) -> UserRead:
    """The only door to the moderator role, and it opens for one person with one link.

    No CSRF gate, like the other registrations: the caller has no session to ride on yet.
    What stands in for it is the invitation itself — 32 random bytes bound to one address,
    spent in a single statement, behind an attempt limit.
    """
    user = await invitations.accept(
        session,
        payload.token,
        payload.normalized_email,
        payload.password.get_secret_value(),
    )
    tokens = await auth_service.issue_tokens(
        session, settings, user, request.headers.get("user-agent")
    )
    await session.commit()
    set_auth_cookies(response, settings, tokens)
    return UserRead.model_validate(user)


@router.post("/login", response_model=UserRead)
async def login(
    payload: LoginRequest,
    response: Response,
    request: Request,
    settings: SettingsDep,
    session: SessionDep,
) -> UserRead:
    user = await auth_service.authenticate(
        session, payload.normalized_email, payload.password.get_secret_value()
    )
    tokens = await auth_service.issue_tokens(
        session, settings, user, request.headers.get("user-agent")
    )
    await session.commit()
    set_auth_cookies(response, settings, tokens)
    return UserRead.model_validate(user)


@router.post("/refresh", response_model=UserRead, dependencies=[Depends(require_csrf)])
async def refresh(
    request: Request, response: Response, settings: SettingsDep, session: SessionDep
) -> UserRead:
    raw_refresh = request.cookies.get(settings.refresh_cookie_name)
    if not raw_refresh:
        raise AuthenticationError("Сессия недействительна, войдите заново")
    user, tokens = await auth_service.rotate_refresh_token(
        session, settings, raw_refresh, request.headers.get("user-agent")
    )
    await session.commit()
    set_auth_cookies(response, settings, tokens)
    return UserRead.model_validate(user)


@router.post(
    "/logout", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_csrf)]
)
async def logout(
    request: Request, response: Response, settings: SettingsDep, session: SessionDep
) -> None:
    raw_refresh = request.cookies.get(settings.refresh_cookie_name)
    if raw_refresh:
        await auth_service.revoke_refresh_token(session, raw_refresh)
        await session.commit()
    clear_auth_cookies(response, settings)


@router.post("/email", response_model=MessageResponse, dependencies=[Depends(require_csrf)])
async def change_email(
    payload: EmailChangeRequest,
    user: CurrentUser,
    response: Response,
    settings: SettingsDep,
    session: SessionDep,
) -> MessageResponse:
    was = await auth_service.change_email(
        session, user, payload.current_password.get_secret_value(), payload.normalized_email
    )
    await audit.record(session, user, "user.email_changed", ENTITY, user.id, **{"from": was})
    await session.commit()
    # the address is half of the credentials, so the sessions holding the old one ended with it
    clear_auth_cookies(response, settings)
    return MessageResponse(message="Логин изменён, войдите заново")


@router.post("/password", response_model=MessageResponse, dependencies=[Depends(require_csrf)])
async def change_password(
    payload: PasswordChangeRequest,
    user: CurrentUser,
    response: Response,
    settings: SettingsDep,
    session: SessionDep,
) -> MessageResponse:
    await auth_service.change_password(
        session,
        user,
        payload.current_password.get_secret_value(),
        payload.password.get_secret_value(),
    )
    await audit.record(session, user, "user.password_changed", ENTITY, user.id)
    await session.commit()
    # every session ended with the change, so the cookies in hand are stale
    clear_auth_cookies(response, settings)
    return MessageResponse(message="Пароль изменён, войдите заново")


@router.post(
    "/password-reset/request",
    response_model=MessageResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def request_password_reset(
    payload: PasswordResetRequest, settings: SettingsDep, session: SessionDep
) -> MessageResponse:
    await auth_service.request_password_reset(session, settings, payload.normalized_email)
    await session.commit()
    # the same answer for known and unknown addresses — otherwise this endpoint lists accounts
    return MessageResponse(message="Если аккаунт существует, на почту отправлена инструкция")


@router.post("/password-reset/confirm", response_model=MessageResponse)
async def confirm_password_reset(
    payload: PasswordResetConfirmRequest,
    response: Response,
    settings: SettingsDep,
    session: SessionDep,
) -> MessageResponse:
    await auth_service.reset_password(session, payload.token, payload.password.get_secret_value())
    await session.commit()
    # every session was revoked with the password change, so the current cookies are stale
    clear_auth_cookies(response, settings)
    return MessageResponse(message="Пароль изменён, войдите заново")
