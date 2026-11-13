"""The shape of the three cookies a session travels in.

What is asserted here is not decoration. `__Host-` is a promise the browser keeps for us: it
refuses to store such a cookie unless it is Secure, carries no Domain and sits at the root, and
it will not let a neighbouring subdomain overwrite it. Lose the prefix and the guarantee goes
back to being something we merely intend.
"""

from fastapi import Response

from app.core.config import Settings, get_settings
from app.core.cookies import clear_session_cookies, set_session_cookies
from app.services.sessions import IssuedSession

ISSUED = IssuedSession(token="a-session-token", csrf_token="a-csrf-token")


def _deployed() -> Settings:
    return get_settings().model_copy(update={"app_env": "production"})


def _cookies(settings: Settings) -> dict[str, str]:
    response = Response()
    set_session_cookies(response, settings, ISSUED)
    return {line.split("=", 1)[0]: line for line in response.headers.getlist("set-cookie")}


def test_no_cookie_carries_a_domain() -> None:
    """A Domain cookie is sent to every subdomain, which is how one hijacked storefront
    becomes a session for the whole platform."""
    for line in _cookies(_deployed()).values():
        assert "domain=" not in line.lower(), line


def test_the_session_and_the_csrf_token_are_host_locked() -> None:
    settings = _deployed()
    issued = _cookies(settings)

    for name in (settings.session_cookie, settings.csrf_cookie):
        assert name.startswith("__Host-")
        line = issued[name].lower()
        assert "secure" in line
        assert "path=/;" in line or line.rstrip().endswith("path=/")


def test_there_is_no_second_cookie_to_scope() -> None:
    """The refresh token had to settle for `__Secure-` and a narrow path, because `__Host-`
    demands Path=/ and a credential that could renew a session should not ride on every
    request for a photo. One server-side session leaves nothing to make that trade about."""
    assert len(_cookies(_deployed())) == 2


def test_the_local_stand_keeps_the_bare_names() -> None:
    """Both prefixes require Secure, which plain http cannot offer: a prefixed cookie there
    would simply be dropped, and the stand would have no session at all."""
    settings = get_settings()
    assert settings.is_local

    issued = _cookies(settings)

    assert settings.session_cookie == settings.session_cookie_name
    assert not any(name.startswith("__") for name in issued)
    assert "secure" not in issued[settings.session_cookie].lower()


def test_only_the_csrf_token_is_readable_by_scripts() -> None:
    """The client has to echo it back in a header; the other two it must never touch."""
    settings = _deployed()
    issued = _cookies(settings)

    assert "httponly" in issued[settings.session_cookie].lower()
    assert "httponly" not in issued[settings.csrf_cookie].lower()


def test_clearing_uses_the_same_names_and_paths() -> None:
    """A cookie deleted at the wrong path is not deleted, only shadowed."""
    settings = _deployed()
    response = Response()

    clear_session_cookies(response, settings)

    cleared = response.headers.getlist("set-cookie")
    assert any(settings.session_cookie in line for line in cleared)
    assert any(settings.csrf_cookie in line for line in cleared)
