"""The pause in the middle of signing in, while the second factor is asked for.

A correct password no longer opens a session for an account that has an authenticator. It
leaves a short-lived signed note saying who got that far, and the session is opened by
`/auth/login/totp` when the code arrives.

Lives here rather than beside the routes because three of them need it: the password sign-in
raises it, the Google callback raises it, and the route that finishes the job reads it.

**Signed**, because a cookie the caller can write is a cookie the caller can use to claim they
are halfway into somebody else's account. **Short-lived**, because this note plus a stolen
password is the account, and it should not sit in a browser overnight. **`SameSite=Lax`**,
which is also what protects the route that reads it: a cross-site POST does not carry it, so
a forged request arrives with nobody waiting.
"""

from fastapi import Request, Response

from app.core.config import Settings
from app.core.cookies import cookie_header
from app.core.errors import AuthenticationError
from app.core.sealed import seal, unseal
from app.models import User

COOKIE = "allstore_totp"
# Long enough to find a telephone, short enough that an abandoned one is gone before it matters.
TTL_SECONDS = 300


class SecondFactorRequired(AuthenticationError):
    """The password was right and that is no longer the whole question.

    Carries the note in a `Set-Cookie` header, because a refusal is rendered by the exception
    handler and never sees the route's own response object.
    """

    code = "totp_required"

    def __init__(self, message: str, cookie: str) -> None:
        super().__init__(message)
        self._cookie = cookie

    @property
    def headers(self) -> dict[str, str]:
        return {"set-cookie": self._cookie}


def pause(settings: Settings, user: User) -> SecondFactorRequired:
    """Built by the sign-in paths — password and Google alike — and raised by them."""
    return SecondFactorRequired(
        "Введите код из приложения-аутентификатора",
        cookie_header(
            COOKIE, seal(settings, {"user": str(user.id)}), settings, max_age=TTL_SECONDS
        ),
    )


def remember(response: Response, settings: Settings, user: User) -> None:
    """The same note, written on a response that is going out anyway.

    For the Google path, which answers a browser that has just come back from an external
    site: it must land on a page, not on a JSON refusal, so the pause is a redirect to the
    sign-in screen with this cookie attached rather than an error carrying one.
    """
    response.set_cookie(
        COOKIE,
        seal(settings, {"user": str(user.id)}),
        max_age=TTL_SECONDS,
        httponly=True,
        secure=not settings.is_local,
        samesite="lax",
        path="/",
    )


def waiting_for(request: Request, settings: Settings) -> str | None:
    """Who, if anybody, is halfway into signing in on this browser."""
    payload = unseal(settings, request.cookies.get(COOKIE), max_age_seconds=TTL_SECONDS)
    return None if payload is None else payload.get("user")
