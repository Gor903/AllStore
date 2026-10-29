import asyncio

from fastapi import APIRouter, BackgroundTasks, Depends, Request, Response, status

from app.core.client_ip import client_ip
from app.core.config import Settings
from app.core.cookies import clear_session_cookies, set_session_cookies
from app.deps.auth import (
    CurrentSession,
    CurrentUser,
    SessionDep,
    SettingsDep,
    SignedInUser,
    require_bound_csrf,
    require_csrf,
)
from app.deps.rate_limit import (
    delay_for_account,
    forget_account_delay,
    limit_credential_change,
    limit_login,
    limit_registration,
    limit_reset_confirm,
    limit_reset_request,
)
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
    VerifyRequest,
)
from app.services import audit, device_keys, notifications
from app.services import auth as auth_service
from app.services import sessions as session_service

router = APIRouter(prefix="/auth", tags=["auth"])

# what these entries are about: the account itself, not anything it owns
ENTITY = "user"


def _context(request: Request, settings: Settings) -> dict[str, str | None]:
    """What a session remembers about where it began, for the device list to show."""
    return {
        "ip": client_ip(request, settings),
        "user_agent": request.headers.get("user-agent"),
    }


@router.post(
    "/register/buyer",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(limit_registration)],
)
async def register_buyer(
    payload: BuyerRegisterRequest,
    response: Response,
    request: Request,
    settings: SettingsDep,
    session: SessionDep,
) -> UserRead:
    user = await auth_service.register_buyer(session, payload)
    issued = await session_service.open_session(
        session, settings, user, **_context(request, settings)
    )
    await session.commit()
    set_session_cookies(response, settings, issued)
    return UserRead.model_validate(user)


@router.post(
    "/register/seller",
    response_model=SellerRegisterResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(limit_registration)],
)
async def register_seller(
    payload: SellerRegisterRequest,
    response: Response,
    request: Request,
    settings: SettingsDep,
    session: SessionDep,
) -> SellerRegisterResponse:
    user, business = await auth_service.register_seller(session, payload)
    issued = await session_service.open_session(
        session, settings, user, **_context(request, settings)
    )
    await session.commit()
    set_session_cookies(response, settings, issued)
    return SellerRegisterResponse.model_validate({"user": user, "business": business})


@router.post("/login", response_model=UserRead, dependencies=[Depends(limit_login)])
async def login(
    payload: LoginRequest,
    response: Response,
    request: Request,
    settings: SettingsDep,
    session: SessionDep,
) -> UserRead:
    # Paid before anything is looked up, and keyed on the address as typed: an account that
    # does not exist waits exactly as long as one that does, so the wait says nothing about
    # which. The limiter above counts the address the request came from; this one counts the
    # account being guessed at, and slows rather than refuses — see GraduatedDelay.
    waiting = delay_for_account(request, payload.normalized_email)
    if waiting > 0:
        await asyncio.sleep(waiting)
    user = await auth_service.authenticate(
        session, payload.normalized_email, payload.password.get_secret_value()
    )
    # they proved the account is theirs, so the guesses that came before them stop counting
    forget_account_delay(request, payload.normalized_email)
    issued = await session_service.open_session(
        session, settings, user, **_context(request, settings)
    )
    await session.commit()
    set_session_cookies(response, settings, issued)
    return UserRead.model_validate(user)


@router.post(
    "/renew",
    response_model=UserRead,
    dependencies=[Depends(require_bound_csrf)],
)
async def renew(
    request: Request,
    row: CurrentSession,
    user: SignedInUser,
    response: Response,
    settings: SettingsDep,
    session: SessionDep,
) -> UserRead:
    """Asks for a fresh token now rather than when it is due.

    For a session with no device key this is a convenience: the server renews such sessions
    by itself on whatever request is in flight when a token gets old enough. For a bound one
    it is the only way, because only the browser can sign the proof — and renewal is exactly
    the moment binding exists to protect.
    """
    if row.device_public_key is not None:
        issued_at = device_keys.verify(
            row,
            request.headers.get(device_keys.HEADER),
            method=request.method,
            url=str(request.url),
        )
        await device_keys.remember(session, row, issued_at)
    issued = await session_service.renew(session, settings, row)
    await session.commit()
    set_session_cookies(response, settings, issued)
    return UserRead.model_validate(user)


@router.post(
    "/verify",
    response_model=MessageResponse,
    dependencies=[Depends(require_bound_csrf), Depends(limit_credential_change)],
)
async def verify_password(
    payload: VerifyRequest,
    row: CurrentSession,
    user: SignedInUser,
    session: SessionDep,
) -> MessageResponse:
    """Proves the password again, for the actions that will not take a session's word for it.

    No new session and no new cookie: this is the same session saying it is still the person
    who opened it, and `verified_at` is where that is written down.
    """
    await auth_service.verify_password_of(user, payload.password.get_secret_value())
    await session_service.mark_verified(session, row)
    await session.commit()
    return MessageResponse(message="Пароль подтверждён")


@router.post(
    "/logout", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_csrf)]
)
async def logout(
    request: Request, response: Response, settings: SettingsDep, session: SessionDep
) -> None:
    """Deliberately forgiving: a session that is already gone still leaves with its cookies
    cleared, because the one thing somebody pressing "sign out" must never see is a refusal."""
    token = request.cookies.get(settings.session_cookie)
    if token:
        row = await session_service.peek(session, settings, token)
        if row is not None:
            await session_service.sign_out(session, row)
            await session.commit()
    clear_session_cookies(response, settings)


@router.post(
    "/email",
    response_model=MessageResponse,
    dependencies=[Depends(require_bound_csrf), Depends(limit_credential_change)],
)
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
    clear_session_cookies(response, settings)
    return MessageResponse(message="Логин изменён, войдите заново")


@router.post(
    "/password",
    response_model=MessageResponse,
    dependencies=[Depends(require_bound_csrf), Depends(limit_credential_change)],
)
async def change_password(
    payload: PasswordChangeRequest,
    # the one route an account owing a change must reach, and the reason SignedInUser exists
    user: SignedInUser,
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
    clear_session_cookies(response, settings)
    return MessageResponse(message="Пароль изменён, войдите заново")


@router.post(
    "/password-reset/request",
    response_model=MessageResponse,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(limit_reset_request)],
)
async def request_password_reset(
    payload: PasswordResetRequest,
    background: BackgroundTasks,
    settings: SettingsDep,
    session: SessionDep,
) -> MessageResponse:
    letter = await auth_service.request_password_reset(session, settings, payload.normalized_email)
    # committed before the letter is scheduled: the link must not be able to arrive before the
    # token it points at exists
    await session.commit()
    if letter is not None:
        # after the answer, so the time it takes to reach somebody else's mail server is not
        # part of what this endpoint tells the caller
        background.add_task(notifications.deliver, settings, letter)
    # the same answer for known and unknown addresses — otherwise this endpoint lists accounts
    return MessageResponse(message="Если аккаунт существует, на почту отправлена инструкция")


@router.post(
    "/password-reset/confirm",
    response_model=MessageResponse,
    dependencies=[Depends(limit_reset_confirm)],
)
async def confirm_password_reset(
    payload: PasswordResetConfirmRequest,
    response: Response,
    settings: SettingsDep,
    session: SessionDep,
) -> MessageResponse:
    await auth_service.reset_password(session, payload.token, payload.password.get_secret_value())
    await session.commit()
    # every session was revoked with the password change, so the current cookies are stale
    clear_session_cookies(response, settings)
    return MessageResponse(message="Пароль изменён, войдите заново")
