"""Signing in with Google, and the three refusals that make it safe.

**The code is exchanged here, never in the browser.** The authorization code travels back
through the visitor, so it is assumed to be seen; what turns it into a session is the client
secret, which lives on this side, plus a PKCE verifier the browser kept to itself. A code
intercepted on its way back buys nothing without both.

**The identity is `sub`, never the address.** Google's subject is stable and belongs to one
account forever. An address is a label its owner can change, and at a company it can pass
between people — keying on it would mean that acquiring an old address acquires the account
it used to point at.

**A matching address does not join two accounts.** Signing in with Google at an address that
already has a password account is refused, with the way forward spelled out: sign in the
ordinary way and link from the settings. The alternative is that anybody who can persuade a
provider to assert an address can take the account behind it.

What Google asserts is believed only after the ID token is checked in full — signature
against the published keys, issuer, audience, expiry, and the nonce this browser was given.
A token missing any of those is a token somebody else made.
"""

import base64
import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx
import jwt
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import ConflictError, PermissionDeniedError
from app.core.logging import get_logger
from app.models import IdentityProvider, User, UserIdentity, UserRole
from app.repositories import identities, users

logger = get_logger(__name__)

# Only what is needed to know who this is. Anything more is something to explain later.
SCOPE = "openid email profile"
ISSUERS = frozenset({"https://accounts.google.com", "accounts.google.com"})


class GoogleNotOffered(PermissionDeniedError):
    """No client credentials, so the platform does not offer this way in at all."""

    code = "google_not_configured"


class GoogleRefused(PermissionDeniedError):
    """Something in the round trip did not add up. Deliberately one code for all of them:
    a caller learning which check failed learns how to approach the next attempt."""

    code = "google_refused"


class AddressBelongsToAPasswordAccount(ConflictError):
    """The address is somebody's already, and that somebody signs in with a password.

    Said plainly rather than hidden, because the person reading it is almost always the owner
    and the way forward is specific: sign in as you always have, then link Google from the
    settings. Hiding it would leave them at a dead end with no idea why.
    """

    code = "link_from_settings"


class StaffMustUseTheirOwnAddress(ConflictError):
    """A moderator or an administrator attaching a Google account on another address."""

    code = "staff_address_mismatch"


# Roles whose Google account has to be the one on the account's own address.
STAFF = (UserRole.ADMIN, UserRole.MODERATOR)


@dataclass(frozen=True)
class Handshake:
    """What the browser is sent away with, and what has to come back with it."""

    url: str
    state: str
    nonce: str
    verifier: str


@dataclass(frozen=True)
class Assertion:
    """What Google says, once it has been checked."""

    subject: str
    email: str


def _secret(settings: Settings) -> str:
    if settings.google_client_secret is None:
        return ""
    return settings.google_client_secret.get_secret_value()


def is_offered(settings: Settings) -> bool:
    return bool(settings.google_client_id and settings.google_client_secret)


def _ensure_offered(settings: Settings) -> None:
    if not is_offered(settings):
        raise GoogleNotOffered("Вход через Google на площадке не настроен")


async def _discover(settings: Settings) -> dict[str, Any]:
    """Asked for each time rather than cached at import.

    Google rotates these endpoints and publishes the current ones; a value frozen at start-up
    is a value that is right until the morning it is not.
    """
    async with httpx.AsyncClient(timeout=settings.google_timeout_seconds) as client:
        response = await client.get(settings.google_discovery_url)
        response.raise_for_status()
        discovered: dict[str, Any] = response.json()
        return discovered


def begin(settings: Settings, redirect_uri: str, authorization_endpoint: str) -> Handshake:
    """Builds the address to send the browser to, and the secrets to check its return by."""
    _ensure_offered(settings)
    state = secrets.token_urlsafe(24)
    nonce = secrets.token_urlsafe(24)
    # plain rather than S256 is allowed by the spec and is the wrong choice: it would make
    # the verifier recoverable from the challenge, which is the whole thing PKCE protects
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
    challenge_text = challenge.decode().rstrip("=")
    query = httpx.QueryParams(
        {
            "client_id": settings.google_client_id or "",
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": SCOPE,
            "state": state,
            "nonce": nonce,
            "code_challenge": challenge_text,
            "code_challenge_method": "S256",
        }
    )
    return Handshake(f"{authorization_endpoint}?{query}", state, nonce, verifier)


async def start(settings: Settings, redirect_uri: str) -> Handshake:
    _ensure_offered(settings)
    discovered = await _discover(settings)
    return begin(settings, redirect_uri, str(discovered["authorization_endpoint"]))


async def finish(
    settings: Settings, code: str, verifier: str, nonce: str, redirect_uri: str
) -> Assertion:
    """Turns the code into something Google has signed, and checks every word of it."""
    _ensure_offered(settings)
    discovered = await _discover(settings)
    async with httpx.AsyncClient(timeout=settings.google_timeout_seconds) as client:
        try:
            exchanged = await client.post(
                str(discovered["token_endpoint"]),
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": redirect_uri,
                    "client_id": settings.google_client_id or "",
                    "client_secret": _secret(settings),
                    "code_verifier": verifier,
                },
            )
            exchanged.raise_for_status()
            keys = await client.get(str(discovered["jwks_uri"]))
            keys.raise_for_status()
        except httpx.HTTPError as failed:
            # the caller learns nothing about which half of the round trip went wrong
            logger.warning("google refused the exchange: %s", failed)
            raise GoogleRefused("Google не подтвердил вход") from failed

    raw_token = exchanged.json().get("id_token")
    if not isinstance(raw_token, str):
        raise GoogleRefused("Google не подтвердил вход")
    return _read(settings, raw_token, keys.json(), nonce)


def _read(settings: Settings, raw_token: str, jwks: dict[str, Any], nonce: str) -> Assertion:
    try:
        key = jwt.PyJWKSet.from_dict(jwks)[jwt.get_unverified_header(raw_token)["kid"]]
        claims = jwt.decode(
            raw_token,
            key.key,
            algorithms=["RS256"],
            audience=settings.google_client_id,
            options={"require": ["exp", "iat", "aud", "iss", "sub"]},
        )
    except (jwt.PyJWTError, KeyError, AttributeError) as bad:
        raise GoogleRefused("Google не подтвердил вход") from bad

    if claims.get("iss") not in ISSUERS:
        raise GoogleRefused("Google не подтвердил вход")
    # the nonce ties this token to the browser that started the handshake, which is what
    # stops one obtained elsewhere from being replayed here
    if not secrets.compare_digest(str(claims.get("nonce", "")), nonce):
        raise GoogleRefused("Google не подтвердил вход")
    # an address Google itself has not confirmed proves nothing about who is holding it
    if claims.get("email_verified") is not True:
        raise GoogleRefused("Google не подтвердил этот адрес")
    email = str(claims.get("email", "")).strip().lower()
    if not email:
        raise GoogleRefused("Google не сообщил адрес")
    return Assertion(subject=str(claims["sub"]), email=email)


async def sign_in(session: AsyncSession, assertion: Assertion, role: UserRole) -> tuple[User, bool]:
    """Finds the account this subject already opens, or makes one. Says which it was."""
    identity = await identities.get(session, IdentityProvider.GOOGLE, assertion.subject)
    if identity is not None:
        identity.last_login_at = _now()
        user = await users.get_by_id(session, identity.user_id)
        if user is None:
            raise GoogleRefused("Google не подтвердил вход")
        return user, False

    existing = await users.get_by_email(session, assertion.email)
    if existing is not None:
        raise AddressBelongsToAPasswordAccount(
            "На этот адрес уже есть аккаунт. Войдите обычным способом и привяжите Google "
            "в настройках — так мы будем уверены, что это вы."
        )

    user = await users.add(
        session,
        User(
            email=assertion.email,
            # no password at all, rather than one nobody chose: a value here would be a value
            # somebody could try to guess against
            password_hash=None,
            role=role,
            # Google says it checked the address, and that is the same thing our own letter
            # establishes — asking again would be asking the person to prove it twice
            email_verified_at=_now(),
        ),
    )
    await identities.add(
        session,
        UserIdentity(
            user_id=user.id,
            provider=IdentityProvider.GOOGLE,
            provider_subject=assertion.subject,
            email_at_link=assertion.email,
            last_login_at=_now(),
        ),
    )
    return user, True


async def link(session: AsyncSession, user: User, assertion: Assertion) -> UserIdentity:
    """Attaches a Google account to one that already exists, from inside its own session.

    A moderator or an administrator may attach only a Google account on the same address as
    the one they administer with. Everybody else may attach any of theirs.

    The difference is not about trusting the person — they are signed in and have just proved
    their password. It is about what an administrator's account is: a seat with a name on it
    that somebody else will one day have to audit, and a second door into it through a
    personal mailbox the platform knows nothing about is a door nobody can account for. For a
    buyer the same freedom is simply convenience, and convenience is the point of the feature.
    """
    if user.role in STAFF and user.email != assertion.email:
        raise StaffMustUseTheirOwnAddress(
            "Привязать можно только аккаунт Google на том же адресе, что и у этого аккаунта"
        )
    taken = await identities.get(session, IdentityProvider.GOOGLE, assertion.subject)
    if taken is not None:
        if taken.user_id == user.id:
            return taken
        raise AddressBelongsToAPasswordAccount(
            "Этот аккаунт Google уже привязан к другому аккаунту на площадке"
        )
    return await identities.add(
        session,
        UserIdentity(
            user_id=user.id,
            provider=IdentityProvider.GOOGLE,
            provider_subject=assertion.subject,
            email_at_link=assertion.email,
        ),
    )


def _now() -> datetime:
    return datetime.now(UTC)
