import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import APIRouter, Depends, Request, Response, status

from app.core.client_ip import client_ip
from app.core.config import Settings
from app.core.cookies import clear_session_cookies, set_session_cookies
from app.core.errors import AppError
from app.core.half_sign_in import pause as pause_for_second_factor
from app.core.logging import get_logger
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
from app.models import User
from app.repositories import sessions as sessions_repo
from app.schemas.auth import (
    BuyerRegisterRequest,
    EmailChangeRequest,
    EmailConfirmRequest,
    LoginRequest,
    MessageResponse,
    PasswordChangeRequest,
    PasswordResetConfirmRequest,
    PasswordResetRequest,
    SellerRegisterRequest,
    UserRead,
    VerifyRequest,
)
from app.services import audit, device_keys, email_verification, notifications
from app.services import auth as auth_service
from app.services import sessions as session_service
from app.services import totp as totp_service

router = APIRouter(prefix="/auth", tags=["auth"])

logger = get_logger(__name__)

# what these entries are about: the account itself, not anything it owns
ENTITY = "user"

# One sentence for both outcomes of registration. It promises a letter and nothing else,
# because a letter is the only thing that happens in both cases.
REGISTERED = "Если адрес свободен, на него отправлено письмо со ссылкой для подтверждения"


async def _register(
    session: SessionDep,
    settings: Settings,
    payload: BuyerRegisterRequest,
    create: Callable[[SessionDep, Any], Awaitable[User]],
) -> None:
    """Creates the account, or writes to whoever already holds the address.

    Both paths end with exactly one letter sent and nothing returned, so the caller has
    nothing to tell them apart by.
    """
    await auth_service.ensure_password_is_still_a_secret(
        settings, payload.password.get_secret_value()
    )
    try:
        user = await create(session, payload)
    except auth_service.AddressAlreadyTaken:
        await session.commit()
        notifications.deliver(
            settings,
            notifications.registration_attempt_letter(settings, payload.normalized_email),
        )
        return
    letters = await email_verification.request(session, settings, user, user.email)
    await session.commit()
    notifications.deliver(settings, letters.confirm)


def _context(request: Request, settings: Settings) -> dict[str, str | None]:
    """What a session remembers about where it began, for the device list to show."""
    return {
        "ip": client_ip(request, settings),
        "user_agent": request.headers.get("user-agent"),
    }


@router.post(
    "/register/buyer",
    response_model=MessageResponse,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(limit_registration)],
)
async def register_buyer(
    payload: BuyerRegisterRequest,
    settings: SettingsDep,
    session: SessionDep,
) -> MessageResponse:
    """Answers the same way whether the address was free or not.

    It used to refuse a taken address out loud, which made this form a way of asking whether
    a particular person has an account here — it needs no password and anybody can walk a
    list of addresses through it. Now both outcomes get this sentence, and the difference
    lives where it belongs: in who receives a letter and what it says.

    No session either, for the same reason. Signing one person in and not the other is a
    difference a caller can see without reading a word.
    """
    await _register(session, settings, payload, auth_service.register_buyer)
    return MessageResponse(message=REGISTERED)


@router.post(
    "/register/seller",
    response_model=MessageResponse,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(limit_registration)],
)
async def register_seller(
    payload: SellerRegisterRequest,
    settings: SettingsDep,
    session: SessionDep,
) -> MessageResponse:
    """The same answer as the buyer path, for the same reason. The shop is created with the
    account and waits for a moderator either way."""

    async def _create(db: SessionDep, data: SellerRegisterRequest) -> User:
        user, _business = await auth_service.register_seller(db, data)
        return user

    await _register(session, settings, payload, _create)
    return MessageResponse(message=REGISTERED)


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
    waiting = await delay_for_account(request, payload.normalized_email)
    if waiting > 0:
        await asyncio.sleep(waiting)
    try:
        user = await auth_service.authenticate(
            session, settings, payload.normalized_email, payload.password.get_secret_value()
        )
    except AppError as refusal:
        # Logged, deliberately not written to the journal. The journal is the record of
        # deliberate acts by people the platform can name, and it is never pruned; a row per
        # failed guess would let an anonymous caller fill it at the limiter's pace and bury
        # the moderation record underneath. A log line costs nothing, has a retention policy,
        # and is what a "burst of failed sign-ins" alert would be built on anyway. The
        # successful half is not logged here because it is already recorded properly, in
        # `sessions` — with the address, the device, the method and the time.
        logger.warning(
            "sign-in refused for %s from %s: %s",
            payload.normalized_email,
            client_ip(request, settings),
            refusal.code,
        )
        raise
    # they proved the account is theirs, so the guesses that came before them stop counting
    await forget_account_delay(request, payload.normalized_email)
    if await totp_service.in_force(session, user):
        # The password was right and the sign-in is not finished. No session is opened; what
        # the browser gets is a short-lived note saying who got this far, and the code it has
        # to answer with goes to /auth/login/totp.
        raise pause_for_second_factor(settings, user)
    # asked before the new session exists, so it means "was it already open somewhere"
    opened_elsewhere = await sessions_repo.has_live_family(session, user.id)
    context = _context(request, settings)
    issued = await session_service.open_session(session, settings, user, **context)
    await session.commit()
    if opened_elsewhere:
        # only when the account was already open somewhere: a letter for every one of
        # somebody's own daily logins is a letter they stop reading
        notifications.deliver(
            settings,
            notifications.new_device_letter(
                settings, user.email, context["user_agent"], context["ip"]
            ),
        )
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
    settings: SettingsDep,
    session: SessionDep,
) -> MessageResponse:
    """Asks the new address to answer. Nothing moves until it does.

    This used to change the login on the spot, which meant a typo in the new address locked
    the owner out of their own account: the password was right and the login was a place
    nobody could read. The session is deliberately left alone — it ends when the move actually
    happens, not when somebody merely asks for one.
    """
    await auth_service.verify_password_of(user, payload.current_password.get_secret_value())
    if payload.normalized_email == user.email:
        raise email_verification.AddressUnchangedError("Это и есть текущий логин — менять нечего")
    letters = await email_verification.request(session, settings, user, payload.normalized_email)
    await audit.record(
        session, user, "user.email_change_requested", ENTITY, user.id, to=payload.normalized_email
    )
    await session.commit()
    notifications.deliver(settings, letters.confirm)
    if letters.notice is not None:
        notifications.deliver(settings, letters.notice)
    return MessageResponse(message="Ссылка отправлена на новый адрес, подтвердите его")


@router.post(
    "/email/verify",
    response_model=MessageResponse,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_bound_csrf), Depends(limit_credential_change)],
)
async def request_email_verification(
    user: SignedInUser,
    settings: SettingsDep,
    session: SessionDep,
) -> MessageResponse:
    """Sends the confirmation letter again, for the address the account already has."""
    letters = await email_verification.request(session, settings, user, user.email)
    await session.commit()
    notifications.deliver(settings, letters.confirm)
    return MessageResponse(message="Письмо отправлено, проверьте почту")


@router.post("/email/confirm", response_model=MessageResponse)
async def confirm_email(
    payload: EmailConfirmRequest,
    response: Response,
    settings: SettingsDep,
    session: SessionDep,
) -> MessageResponse:
    """Spends the link. Needs no session of its own: the token is the proof, and the person
    opening it may well be on a device that was never signed in."""
    outcome = await email_verification.confirm(session, payload.token)
    user = outcome.user
    await audit.record(session, user, "user.email_verified", ENTITY, user.id, email=user.email)
    await session.commit()
    if outcome.moved:
        # a move ends every session, so whatever cookies this browser holds are stale.
        # Confirming the address you registered with is not a move and does not sign you out.
        clear_session_cookies(response, settings)
        return MessageResponse(message="Адрес изменён, войдите заново")
    return MessageResponse(message="Адрес подтверждён")


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
    await auth_service.ensure_password_is_still_a_secret(
        settings, payload.password.get_secret_value()
    )
    await auth_service.change_password(
        session,
        user,
        payload.current_password.get_secret_value(),
        payload.password.get_secret_value(),
    )
    await audit.record(session, user, "user.password_changed", ENTITY, user.id)
    await session.commit()
    notifications.deliver(settings, notifications.password_changed_letter(settings, user.email))
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
        notifications.deliver(settings, letter)
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
    await auth_service.ensure_password_is_still_a_secret(
        settings, payload.password.get_secret_value()
    )
    await auth_service.reset_password(session, payload.token, payload.password.get_secret_value())
    await session.commit()
    # every session was revoked with the password change, so the current cookies are stale
    clear_session_cookies(response, settings)
    return MessageResponse(message="Пароль изменён, войдите заново")
