"""The three cookies a session travels in, and where each is allowed to go.

They are host-only. ADR 1 originally put them on `.allstore.am` so that a storefront on a
subdomain shared the visitor's session, and the price of that was never paid only because the
branch never ran: every configuration in the repository is `APP_ENV=local`, where the domain
was already omitted. The price would have been real — a cross-site scripting hole in any one
seller's storefront, or a single hijacked subdomain, would hand over the session for the whole
platform, and a subdomain could plant its own CSRF cookie and satisfy the double submit with
it.

Nothing is lost by refusing to pay it. The browser still sends these to the API from a page on
a storefront host, because `shop.allstore.am` and `allstore.am` are the same site even though
they are different origins. What a subdomain no longer gets is the right to speak for the
session on its own — see the name prefixes in core/config.py, which make the browser enforce
exactly that.
"""

from fastapi import Response

from app.core.config import Settings
from app.services.auth import IssuedTokens


def _refresh_path(settings: Settings) -> str:
    """Narrower than the rest on purpose: a credential that can renew a whole session should
    not ride along on every request for a product image."""
    return f"{settings.api_prefix}/auth"


def set_auth_cookies(response: Response, settings: Settings, tokens: IssuedTokens) -> None:
    secure = not settings.is_local
    response.set_cookie(
        settings.access_cookie,
        tokens.access_token,
        max_age=settings.access_token_ttl_minutes * 60,
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/",
    )
    response.set_cookie(
        settings.refresh_cookie,
        tokens.refresh_token,
        max_age=settings.refresh_token_ttl_days * 24 * 3600,
        httponly=True,
        secure=secure,
        samesite="lax",
        path=_refresh_path(settings),
    )
    # readable by scripts on purpose: the client echoes it back in a header (double submit)
    response.set_cookie(
        settings.csrf_cookie,
        tokens.csrf_token,
        max_age=settings.refresh_token_ttl_days * 24 * 3600,
        httponly=False,
        secure=secure,
        samesite="lax",
        path="/",
    )


def clear_auth_cookies(response: Response, settings: Settings) -> None:
    """Deleted at the same name and path they were set at: a cookie removed at a different
    path is not removed at all, it is merely shadowed until the browser notices."""
    response.delete_cookie(settings.access_cookie, path="/")
    response.delete_cookie(settings.refresh_cookie, path=_refresh_path(settings))
    response.delete_cookie(settings.csrf_cookie, path="/")
