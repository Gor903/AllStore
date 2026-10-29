"""The shape of the three cookies a session travels in.

What is asserted here is not decoration. `__Host-` is a promise the browser keeps for us: it
refuses to store such a cookie unless it is Secure, carries no Domain and sits at the root, and
it will not let a neighbouring subdomain overwrite it. Lose the prefix and the guarantee goes
back to being something we merely intend.
"""

from fastapi import Response

from app.core.config import Settings, get_settings
from app.core.cookies import clear_auth_cookies, set_auth_cookies
from app.services.auth import IssuedTokens

TOKENS = IssuedTokens(access_token="access", refresh_token="refresh", csrf_token="csrf")


def _deployed() -> Settings:
    return get_settings().model_copy(update={"app_env": "production"})


def _cookies(settings: Settings) -> dict[str, str]:
    response = Response()
    set_auth_cookies(response, settings, TOKENS)
    return {line.split("=", 1)[0]: line for line in response.headers.getlist("set-cookie")}


def test_no_cookie_carries_a_domain() -> None:
    """A Domain cookie is sent to every subdomain, which is how one hijacked storefront
    becomes a session for the whole platform."""
    for line in _cookies(_deployed()).values():
        assert "domain=" not in line.lower(), line


def test_the_session_and_the_csrf_token_are_host_locked() -> None:
    settings = _deployed()
    issued = _cookies(settings)

    for name in (settings.access_cookie, settings.csrf_cookie):
        assert name.startswith("__Host-")
        line = issued[name].lower()
        assert "secure" in line
        assert "path=/;" in line or line.rstrip().endswith("path=/")


def test_the_refresh_token_stays_on_its_own_path() -> None:
    """`__Host-` would demand Path=/, and the narrow path is worth more here: a credential
    that renews a whole session should not ride along on every request for a photo."""
    settings = _deployed()
    line = _cookies(settings)[settings.refresh_cookie]

    assert settings.refresh_cookie.startswith("__Secure-")
    assert "Path=/api/v1/auth" in line
    assert "Secure" in line


def test_the_local_stand_keeps_the_bare_names() -> None:
    """Both prefixes require Secure, which plain http cannot offer: a prefixed cookie there
    would simply be dropped, and the stand would have no session at all."""
    settings = get_settings()
    assert settings.is_local

    issued = _cookies(settings)

    assert settings.access_cookie == settings.access_cookie_name
    assert not any(name.startswith("__") for name in issued)
    assert "secure" not in issued[settings.access_cookie].lower()


def test_only_the_csrf_token_is_readable_by_scripts() -> None:
    """The client has to echo it back in a header; the other two it must never touch."""
    settings = _deployed()
    issued = _cookies(settings)

    assert "httponly" in issued[settings.access_cookie].lower()
    assert "httponly" in issued[settings.refresh_cookie].lower()
    assert "httponly" not in issued[settings.csrf_cookie].lower()


def test_clearing_uses_the_same_names_and_paths() -> None:
    """A cookie deleted at the wrong path is not deleted, only shadowed."""
    settings = _deployed()
    response = Response()

    clear_auth_cookies(response, settings)

    cleared = response.headers.getlist("set-cookie")
    assert any(settings.access_cookie in line for line in cleared)
    assert any(settings.refresh_cookie in line and "Path=/api/v1/auth" in line for line in cleared)
    assert any(settings.csrf_cookie in line for line in cleared)
