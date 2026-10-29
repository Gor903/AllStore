"""The two cookies a session travels in, and where they are allowed to go.

There were three, and the third was the price of ADR 1's pair of tokens: a refresh token that
could only be spent at `/auth/refresh`, scoped to that path so it did not ride along on every
request. One server-side session leaves nothing to scope — see services/sessions.py — so both
of these sit at the root and both can wear `__Host-`.

They are host-only. ADR 1 put them on `.allstore.am` so a storefront on a subdomain shared the
visitor's session, and the price was never actually paid only because the branch never ran:
every configuration in the repository is `APP_ENV=local`, where the domain was already
omitted. The price would have been real — cross-site scripting in any one seller's storefront
would hand over the session for the whole platform.

Nothing is lost by refusing to pay it. The browser still sends these to the API from a page on
a storefront host, because `shop.allstore.am` and `allstore.am` are the same site even though
they are different origins.
"""

from fastapi import Response

from app.core.config import Settings
from app.services.sessions import IssuedSession


def set_session_cookies(response: Response, settings: Settings, issued: IssuedSession) -> None:
    secure = not settings.is_local
    lifetime = settings.session_idle_ttl_days * 24 * 3600
    response.set_cookie(
        settings.session_cookie,
        issued.token,
        max_age=lifetime,
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/",
    )
    # readable by scripts on purpose: the client echoes it back in a header (double submit)
    response.set_cookie(
        settings.csrf_cookie,
        issued.csrf_token,
        max_age=lifetime,
        httponly=False,
        secure=secure,
        samesite="lax",
        path="/",
    )


def cookie_header(
    name: str, value: str, settings: Settings, *, max_age: int, path: str = "/"
) -> str:
    """One `Set-Cookie` line, for a refusal rather than a response.

    A refusal is rendered by the exception handler, which builds its own response — so the
    `Response` a route was given never reaches the browser, and anything set on it is lost.
    That matters in exactly one place: the sign-in that stops to ask for a second factor has
    to leave a cookie saying who got that far. `AppError.headers` is the way through, and
    this builds the line to put in it.

    Formatted by Starlette rather than by hand: the escaping, the date format and the flag
    spelling are all things to get subtly wrong.
    """
    carrier = Response()
    carrier.set_cookie(
        name,
        value,
        max_age=max_age,
        httponly=True,
        secure=not settings.is_local,
        samesite="lax",
        path=path,
    )
    return carrier.headers["set-cookie"]


def clear_session_cookies(response: Response, settings: Settings) -> None:
    """Deleted at the same name and path they were set at: a cookie removed at a different
    path is not removed at all, it is merely shadowed until the browser notices."""
    response.delete_cookie(settings.session_cookie, path="/")
    response.delete_cookie(settings.csrf_cookie, path="/")
