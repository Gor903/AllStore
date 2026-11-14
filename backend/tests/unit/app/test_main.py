"""How the application is assembled, and the three things that assembly decides.

**Where the documentation is.** `/docs` outside local would publish the whole surface of the
platform, including the administrator's routes, to anybody who guessed the path.

**Who may call us from a browser.** Storefront addresses are created when a seller picks a
subdomain, so an exact list is a list that is wrong as soon as a shop opens — without the
pattern a page on `cups.allstore.am` cannot call the API at all, which is how a signed-in
buyer's complaint would stop working the day subdomains shipped.

**Whose allowance is whose.** The limiters are built per application, so each worker keeps its
own tally and a test gets a fresh set with its app instead of inheriting the previous test's.
"""

from typing import Any

import pytest
from fastapi import FastAPI

from app.core.config import Settings, get_settings
from app.deps.rate_limit import Limiters
from app.main import create_app


def _settings(**overrides: Any) -> Settings:
    return get_settings().model_copy(update=overrides)


def _with(monkeypatch: pytest.MonkeyPatch, **overrides: Any) -> FastAPI:
    from app import main

    monkeypatch.setattr(main, "get_settings", lambda: _settings(**overrides))
    return create_app()


def _paths() -> set[str]:
    """What the platform actually answers on, read where the generated client reads it: this
    version of FastAPI keeps included routers folded until the schema is built."""
    return set(create_app().openapi()["paths"])


def _cors(app: FastAPI) -> Any:
    """Middleware is held as a factory, so it is named rather than compared by identity."""
    return next(m for m in app.user_middleware if _named(m) == "CORSMiddleware")


def _named(middleware: Any) -> str:
    return str(getattr(middleware.cls, "__name__", middleware.cls))


def test_the_documentation_is_open_on_a_developer_s_own_machine() -> None:
    app = create_app()

    assert app.docs_url == "/docs"


def test_and_published_nowhere_else(monkeypatch: pytest.MonkeyPatch) -> None:
    """The whole surface of the platform, the administrator's routes included, to anybody who
    guessed the path."""
    app = _with(monkeypatch, app_env="production")

    assert app.docs_url is None
    assert app.redoc_url is None


def test_a_browser_may_call_from_the_addresses_the_platform_was_told_about(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _with(monkeypatch, cors_origins=["https://allstore.am"])

    assert _cors(app).kwargs["allow_origins"] == ["https://allstore.am"]


def test_and_from_any_storefront_by_pattern(monkeypatch: pytest.MonkeyPatch) -> None:
    """A shop's address exists the moment a seller picks it; a list would be stale by then."""
    settings = _settings(cors_origins=["https://allstore.am"])
    app = _with(monkeypatch, cors_origins=["https://allstore.am"])

    assert _cors(app).kwargs["allow_origin_regex"] == settings.storefront_origin_pattern


def test_cookies_travel_on_those_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    """The session lives in a cookie, so a cross-origin call without credentials is a call
    from nobody."""
    app = _with(monkeypatch, cors_origins=["https://allstore.am"])

    assert _cors(app).kwargs["allow_credentials"] is True


def test_nothing_is_allowed_from_a_browser_when_nothing_was_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No origins is not "every origin": the middleware is not added at all."""
    app = _with(monkeypatch, cors_origins=[])

    assert all(_named(m) != "CORSMiddleware" for m in app.user_middleware)


def test_each_application_keeps_its_own_tally() -> None:
    first, second = create_app(), create_app()

    assert isinstance(first.state.limiters, Limiters)
    assert first.state.limiters is not second.state.limiters


def test_the_health_checks_answer_without_the_api_prefix() -> None:
    """A probe is configured once in compose and once in the gateway, and a prefix that moved
    would silently make the stand report itself unhealthy."""
    assert {"/health", "/health/ready"} <= _paths()


def test_everything_else_lives_under_the_one_prefix() -> None:
    settings = get_settings()
    api = {path for path in _paths() if not path.startswith("/health")}

    assert api, "the API is mounted"
    assert all(path.startswith(settings.api_prefix) for path in api)


def test_the_routes_the_platform_is_made_of_are_all_mounted() -> None:
    """A router left out of the factory is a feature that exists in the tree and answers 404."""
    paths = " ".join(_paths())

    for fragment in (
        "/auth/login",
        "/auth/totp",
        "/auth/sessions",
        "/users/me",
        "/stores",
        "/products",
        "/moderation",
        "/storefront",
        "/catalog",
        "/assistant",
        "/admin",
        "/accounts",
        "/reports",
        "/incidents",
    ):
        assert fragment in paths, fragment


def test_a_refusal_comes_out_in_the_one_envelope() -> None:
    """Registered on the application rather than on a router: a handler attached per router
    would be a handler somebody forgets on the next one."""
    app = create_app()

    assert app.exception_handlers
