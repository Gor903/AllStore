"""Enrolling a second factor, and the half-finished sign-in that asks for one.

The pause in the middle of signing in is the interesting part. A correct password no longer
opens a session for an account that has a second factor; it leaves a short-lived signed
cookie saying who got that far, and refuses with a code the client knows how to act on. The
session is opened by `/auth/login/totp`, when the code arrives.

Signed, because a cookie the caller can write is a cookie the caller can use to say they are
halfway into somebody else's account. Short-lived, because it is the one thing standing
between a stolen password and the account, and it should not stand there overnight.
"""

import base64
import io
import uuid

import segno
from fastapi import APIRouter, Depends, Request, Response, status

from app.core.client_ip import client_ip
from app.core.cookies import set_session_cookies
from app.core.errors import AuthenticationError
from app.core.half_sign_in import COOKIE as PENDING_COOKIE
from app.core.half_sign_in import waiting_for
from app.deps.auth import (
    CurrentUser,
    SessionDep,
    SettingsDep,
    UserSettingUpTotp,
    require_bound_csrf,
    require_fresh_verification,
)
from app.deps.rate_limit import limit_second_factor
from app.repositories import sessions as sessions_repo
from app.repositories import totp as totp_repo
from app.schemas.auth import (
    TotpCodeRequest,
    TotpEnrolmentResponse,
    TotpRecoveryResponse,
    TotpStatus,
    UserRead,
)
from app.services import audit, notifications, totp
from app.services import auth as auth_service
from app.services import sessions as session_service

router = APIRouter(prefix="/auth", tags=["totp"])

ENTITY = "user"


@router.get("/totp", response_model=TotpStatus)
async def read_status(user: UserSettingUpTotp, session: SessionDep) -> TotpStatus:
    """Reachable while the second factor is still owed — this is how the client finds out."""
    return TotpStatus(
        enabled=await totp.in_force(session, user),
        required=totp.required_of(user),
        recovery_codes_left=await totp_repo.recovery_codes_left(session, user.id),
    )


@router.post(
    "/totp/setup",
    response_model=TotpEnrolmentResponse,
    dependencies=[Depends(require_bound_csrf)],
)
async def begin_setup(
    user: UserSettingUpTotp, settings: SettingsDep, session: SessionDep
) -> TotpEnrolmentResponse:
    """The secret, once.

    No step-up here, deliberately. An account that is *required* to enrol cannot be asked to
    prove anything beyond the password it just typed — it has no other way to reach this
    screen, and a step-up would be a door locked from the inside. Turning one off is the
    dangerous direction, and that one asks for a code.
    """
    enrolment = await totp.begin(session, settings, user)
    await session.commit()
    return TotpEnrolmentResponse(
        secret=enrolment.secret, uri=enrolment.uri, qr=_qr_data_uri(enrolment.uri)
    )


@router.post(
    "/totp/confirm",
    response_model=TotpRecoveryResponse,
    dependencies=[Depends(require_bound_csrf), Depends(limit_second_factor)],
)
async def confirm_setup(
    payload: TotpCodeRequest,
    user: UserSettingUpTotp,
    settings: SettingsDep,
    session: SessionDep,
) -> TotpRecoveryResponse:
    """A code proves the secret reached a telephone. Until it does, nothing is in force."""
    confirmed = await totp.confirm(session, settings, user, payload.code)
    await audit.record(session, user, "user.totp_enabled", ENTITY, user.id)
    await session.commit()
    notifications.deliver(
        settings, notifications.second_factor_letter(settings, user.email, on=True)
    )
    return TotpRecoveryResponse(recovery_codes=confirmed.recovery_codes)


@router.post(
    "/totp/disable",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[
        Depends(require_bound_csrf),
        Depends(require_fresh_verification),
        Depends(limit_second_factor),
    ],
)
async def disable(
    payload: TotpCodeRequest, user: CurrentUser, settings: SettingsDep, session: SessionDep
) -> None:
    """A step-up and a current code. Taking the second factor off is the one change that makes
    every future sign-in easier for whoever happens to be sitting at the screen."""
    await totp.disable(session, settings, user, payload.code)
    await audit.record(session, user, "user.totp_disabled", ENTITY, user.id)
    await session.commit()
    notifications.deliver(
        settings, notifications.second_factor_letter(settings, user.email, on=False)
    )


@router.post(
    "/login/totp",
    response_model=UserRead,
    dependencies=[Depends(limit_second_factor)],
)
async def finish_sign_in(
    payload: TotpCodeRequest,
    request: Request,
    response: Response,
    settings: SettingsDep,
    session: SessionDep,
) -> UserRead:
    """The second half of signing in: the code, and then the session.

    No CSRF check, for the same reason `/auth/login` has none: there is no session and so no
    token to double-submit. What stands in its place is the pending cookie itself — it is
    `SameSite=Lax`, and a cross-site POST does not carry those, so a forged request arrives
    with nobody waiting and is refused before the code is even read.
    """
    waiting = waiting_for(request, settings)
    if waiting is None:
        raise AuthenticationError("Войдите заново")
    user = await auth_service.get_active_user(session, uuid.UUID(waiting))
    used_recovery = await totp.answer(session, settings, user.id, payload.code)
    # asked before the new session exists, so it means "was it already open somewhere"
    opened_elsewhere = await sessions_repo.has_live_family(session, user.id)
    context = {
        "ip": client_ip(request, settings),
        "user_agent": request.headers.get("user-agent"),
    }
    issued = await session_service.open_session(session, settings, user, **context)
    if used_recovery:
        # Worth a line of its own: a recovery code means the telephone is gone, which is both
        # an ordinary accident and what it looks like when somebody else has the password.
        await audit.record(session, user, "user.totp_recovery_used", ENTITY, user.id)
    await session.commit()
    if used_recovery:
        notifications.deliver(settings, notifications.recovery_code_letter(settings, user.email))
    if opened_elsewhere:
        notifications.deliver(
            settings,
            notifications.new_device_letter(
                settings, user.email, context["user_agent"], context["ip"]
            ),
        )
    set_session_cookies(response, settings, issued)
    response.delete_cookie(PENDING_COOKIE, path="/")
    return UserRead.model_validate(user)


def _qr_data_uri(uri: str) -> str:
    """The link as an image, inline.

    A data URI rather than a file: the policy in the frontend's proxy allows `data:` images
    and forbids every external host, and a QR code that lives at an address is one more thing
    to serve, cache and get the headers wrong on.
    """
    drawn = io.BytesIO()
    segno.make(uri, error="m").save(drawn, kind="svg", scale=4, border=2)
    encoded = base64.b64encode(drawn.getvalue()).decode()
    return f"data:image/svg+xml;base64,{encoded}"
