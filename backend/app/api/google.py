"""The two addresses a browser visits on its way to and from Google, and the linking screen.

The handshake's secrets — the state, the nonce and the PKCE verifier — are carried in one
short-lived, signed, httpOnly cookie rather than in a table. They are worth nothing once the
round trip ends, they belong to one browser, and a table of them would be a table to expire
and sweep. Signed, because a cookie the caller can write is a cookie the caller can use to
answer our own challenge.

Nobody is created as a moderator or an administrator here, whatever the query string says.
Those roles are granted by somebody who already holds one; a provider asserting an address
is not a grant of authority, and the only two roles this file can produce are the two anybody
can register as anyway.
"""

import base64
import hmac
import json
import uuid
from hashlib import sha256
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response, status
from fastapi.responses import RedirectResponse

from app.core.client_ip import client_ip
from app.core.config import Settings
from app.core.cookies import set_session_cookies
from app.core.half_sign_in import remember
from app.deps.auth import (
    CurrentSession,
    CurrentUser,
    OptionalUser,
    SessionDep,
    SettingsDep,
    require_bound_csrf,
    require_fresh_verification,
)
from app.deps.rate_limit import limit_login
from app.models import UserRole
from app.repositories import identities
from app.schemas.session import IdentityList, IdentityRead
from app.services import audit, google_oidc, notifications, totp
from app.services import sessions as session_service

router = APIRouter(prefix="/auth/google", tags=["google"])

ENTITY = "user"
HANDSHAKE_COOKIE = "allstore_google"
# Long enough to sign in with, short enough that an abandoned one is gone before it matters.
HANDSHAKE_TTL_SECONDS = 600

# The only two roles this file can produce. A provider asserting an address is not a grant of
# authority, so moderator and admin are unreachable from here whatever is asked for.
OPEN_ROLES = {"buyer": UserRole.BUYER, "seller": UserRole.SELLER}


def _seal(settings: Settings, payload: dict[str, str]) -> str:
    """base64url, because a cookie value may not contain the commas, quotes and braces JSON
    is made of — left raw, the browser quotes or truncates it and the handshake is lost."""
    body = (
        base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode())
        .decode()
        .rstrip("=")
    )
    mac = hmac.new(settings.secret_key.get_secret_value().encode(), body.encode(), sha256)
    return f"{mac.hexdigest()}.{body}"


def _unseal(settings: Settings, sealed: str | None) -> dict[str, str] | None:
    """Returns what we wrote, or nothing. A cookie that fails this is not an error to explain
    — it is somebody else's, or ours from another day."""
    if not sealed or "." not in sealed:
        return None
    signature, body = sealed.split(".", 1)
    expected = hmac.new(
        settings.secret_key.get_secret_value().encode(), body.encode(), sha256
    ).hexdigest()
    if not hmac.compare_digest(signature, expected):
        return None
    try:
        payload: dict[str, str] = json.loads(
            base64.urlsafe_b64decode(body + "=" * (-len(body) % 4))
        )
    except (json.JSONDecodeError, ValueError):
        return None
    return payload


def _remember(response: Response, settings: Settings, payload: dict[str, str]) -> None:
    response.set_cookie(
        HANDSHAKE_COOKIE,
        _seal(settings, payload),
        max_age=HANDSHAKE_TTL_SECONDS,
        httponly=True,
        secure=not settings.is_local,
        # the browser comes back from accounts.google.com, which is a different site: `strict`
        # would drop the cookie on arrival and break every sign-in
        samesite="lax",
        path="/",
    )


def _redirect_uri(settings: Settings) -> str:
    return f"{settings.public_url}{settings.api_prefix}/auth/google/callback"


async def _leave(settings: Settings, role: str, linking: bool) -> RedirectResponse:
    handshake = await google_oidc.start(settings, _redirect_uri(settings))
    redirect = RedirectResponse(handshake.url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)
    _remember(
        redirect,
        settings,
        {
            "state": handshake.state,
            "nonce": handshake.nonce,
            "verifier": handshake.verifier,
            # kept on our side rather than read back off the query string on return: a role
            # that travels through the browser is a role the browser can edit
            "role": role,
            "link": "1" if linking else "",
        },
    )
    return redirect


@router.get("/start", dependencies=[Depends(limit_login)])
async def start(
    settings: SettingsDep,
    role: Annotated[str, Query(pattern="^(buyer|seller)$")] = "buyer",
) -> RedirectResponse:
    """Sends the browser to Google, having written down what has to come back."""
    return await _leave(settings, role, linking=False)


@router.get("/link", dependencies=[Depends(require_fresh_verification)])
async def start_linking(user: CurrentUser, settings: SettingsDep) -> RedirectResponse:
    """The same journey, from inside an account that already exists.

    Behind a step-up: attaching another way in is as grave as changing the password, and an
    unattended screen must not be enough to add one.
    """
    return await _leave(settings, user.role.value, linking=True)


@router.get("/callback", dependencies=[Depends(limit_login)])
async def callback(
    request: Request,
    viewer: OptionalUser,
    settings: SettingsDep,
    session: SessionDep,
    code: Annotated[str, Query()],
    state: Annotated[str, Query()],
) -> RedirectResponse:
    """Where Google sends the browser back. Everything is checked before anything is believed."""
    remembered = _unseal(settings, request.cookies.get(HANDSHAKE_COOKIE))
    if remembered is None or not hmac.compare_digest(remembered.get("state", ""), state):
        # the state ties this return to the browser that left: without it, anybody could
        # hand somebody else's code to somebody else's session
        raise google_oidc.GoogleRefused("Вход через Google не завершён, попробуйте снова")

    assertion = await google_oidc.finish(
        settings,
        code,
        remembered["verifier"],
        remembered["nonce"],
        _redirect_uri(settings),
    )
    if remembered.get("link"):
        if viewer is None:
            raise google_oidc.GoogleRefused("Войдите в аккаунт, прежде чем привязывать Google")
        await google_oidc.link(session, viewer, assertion)
        await audit.record(
            session, viewer, "user.google_linked", ENTITY, viewer.id, email=assertion.email
        )
        await session.commit()
        notifications.deliver(
            settings,
            notifications.google_link_letter(settings, viewer.email, attached=True),
        )
        linked = RedirectResponse(
            f"{settings.public_url}/devices", status_code=status.HTTP_303_SEE_OTHER
        )
        linked.delete_cookie(HANDSHAKE_COOKIE, path="/")
        return linked

    user, created = await google_oidc.sign_in(
        session, assertion, OPEN_ROLES[remembered.get("role", "buyer")]
    )
    if await totp.in_force(session, user):
        # Staff cannot be created this way, but staff who linked Google can sign in this way —
        # and a second factor only one of the two doors asks for is not a second factor.
        # A redirect rather than a refusal: this browser has just come back from an external
        # site and must land on a page, not on a JSON error it cannot read.
        paused = RedirectResponse(
            f"{settings.public_url}/login?totp=1", status_code=status.HTTP_303_SEE_OTHER
        )
        remember(paused, settings, user)
        paused.delete_cookie(HANDSHAKE_COOKIE, path="/")
        return paused
    issued = await session_service.open_session(
        session,
        settings,
        user,
        ip=client_ip(request, settings),
        user_agent=request.headers.get("user-agent"),
    )
    await audit.record(
        session,
        user,
        "user.google_registered" if created else "user.google_signed_in",
        ENTITY,
        user.id,
        email=assertion.email,
    )
    await session.commit()

    landing = RedirectResponse(
        f"{settings.public_url}/dashboard", status_code=status.HTTP_303_SEE_OTHER
    )
    set_session_cookies(landing, settings, issued)
    landing.delete_cookie(HANDSHAKE_COOKIE, path="/")
    return landing


@router.get("/identities", response_model=IdentityList)
async def list_identities(
    user: CurrentUser, settings: SettingsDep, session: SessionDep
) -> IdentityList:
    """What this account can be signed in with besides its password."""
    rows = await identities.for_user(session, user.id)
    return IdentityList(
        configured=google_oidc.is_offered(settings),
        items=[IdentityRead.model_validate(row) for row in rows],
    )


@router.delete(
    "/identities/{identity_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_bound_csrf)],
)
async def unlink(
    identity_id: uuid.UUID,
    user: CurrentUser,
    current: CurrentSession,
    settings: SettingsDep,
    session: SessionDep,
) -> None:
    """Detaches a provider — unless it is the only way in this account has left.

    An account with no password and no identity is an account nobody can open, including its
    owner, and there is no screen that undoes that.
    """
    rows = await identities.for_user(session, user.id)
    doomed = next((row for row in rows if str(row.id) == str(identity_id)), None)
    if doomed is None:
        raise google_oidc.GoogleRefused("Такой привязки нет")
    if user.password_hash is None and len(rows) == 1:
        raise google_oidc.AddressBelongsToAPasswordAccount(
            "Это единственный способ войти в аккаунт. Сначала задайте пароль."
        )
    await identities.remove(session, doomed)
    await audit.record(session, user, "user.google_unlinked", ENTITY, user.id)
    await session.commit()
    notifications.deliver(
        settings,
        notifications.google_link_letter(settings, user.email, attached=False),
    )
