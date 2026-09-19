from fastapi import Response

from app.core.config import Settings
from app.services.auth import IssuedTokens


def _cookie_domain(settings: Settings) -> str | None:
    """Storefronts live on subdomains, so the cookie is shared across them — except locally,
    where browsers treat a dotted localhost domain as invalid."""
    return None if settings.is_local else f".{settings.base_domain}"


def _refresh_path(settings: Settings) -> str:
    return f"{settings.api_prefix}/auth"


def set_auth_cookies(response: Response, settings: Settings, tokens: IssuedTokens) -> None:
    domain = _cookie_domain(settings)
    secure = not settings.is_local
    response.set_cookie(
        settings.access_cookie_name,
        tokens.access_token,
        max_age=settings.access_token_ttl_minutes * 60,
        httponly=True,
        secure=secure,
        samesite="lax",
        domain=domain,
        path="/",
    )
    response.set_cookie(
        settings.refresh_cookie_name,
        tokens.refresh_token,
        max_age=settings.refresh_token_ttl_days * 24 * 3600,
        httponly=True,
        secure=secure,
        samesite="lax",
        domain=domain,
        path=_refresh_path(settings),
    )
    # readable by scripts on purpose: the client echoes it back in a header (double submit)
    response.set_cookie(
        settings.csrf_cookie_name,
        tokens.csrf_token,
        max_age=settings.refresh_token_ttl_days * 24 * 3600,
        httponly=False,
        secure=secure,
        samesite="lax",
        domain=domain,
        path="/",
    )


def clear_auth_cookies(response: Response, settings: Settings) -> None:
    domain = _cookie_domain(settings)
    response.delete_cookie(settings.access_cookie_name, domain=domain, path="/")
    response.delete_cookie(
        settings.refresh_cookie_name, domain=domain, path=_refresh_path(settings)
    )
    response.delete_cookie(settings.csrf_cookie_name, domain=domain, path="/")
