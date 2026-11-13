"""The pause in the middle of signing in, while the second factor is asked for.

A correct password no longer opens a session for an account that has an authenticator. It
leaves a short-lived signed note saying who got that far, and the session is opened when the
code arrives.

What is asserted here is the note itself: that it is signed rather than merely written, that it
says who without saying anything else, that it is short-lived because this note plus a stolen
password is the account, and that the refusal carrying it reaches the browser at all — it
travels in a `Set-Cookie` on the exception, because a refusal is rendered by the handler and
never sees the route's own response object.
"""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi import FastAPI, Request, status
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.core.config import Settings, get_settings
from app.core.errors import register_exception_handlers
from app.core.half_sign_in import COOKIE, TTL_SECONDS, pause, waiting_for
from app.core.sealed import seal
from app.models import User, UserRole, UserStatus


def _settings(**overrides: object) -> Settings:
    return get_settings().model_copy(
        update={"secret_key": SecretStr("a" * 32), "app_env": "local", **overrides}
    )


def _user() -> User:
    return User(
        id=uuid4(),
        email="person@example.am",
        role=UserRole.MODERATOR,
        status=UserStatus.ACTIVE,
        must_change_password=False,
        created_at=datetime.now(UTC),
    )


def _asking(settings: Settings) -> TestClient:
    """A route that refuses with the pause, and one that reads the note back."""
    app = FastAPI()
    register_exception_handlers(app)
    person = _user()

    @app.post("/login")
    async def login() -> None:
        raise pause(settings, person)

    @app.get("/waiting")
    async def waiting(request: Request) -> dict[str, str | None]:
        return {"user": waiting_for(request, settings), "expected": str(person.id)}

    return TestClient(app)


def test_the_refusal_carries_the_note_to_the_browser() -> None:
    """The handler renders the refusal and never sees the route's response object, so the
    cookie travels on the exception or it does not travel at all."""
    response = _asking(_settings()).post("/login")

    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response.json()["error"]["code"] == "totp_required"
    assert COOKIE in response.cookies


def test_the_browser_that_was_paused_is_the_one_recognised() -> None:
    client = _asking(_settings())

    client.post("/login")
    answer = client.get("/waiting").json()

    assert answer["user"] == answer["expected"]


def test_a_browser_that_was_never_paused_is_waiting_for_nobody() -> None:
    assert _asking(_settings()).get("/waiting").json()["user"] is None


def test_a_note_somebody_wrote_themselves_is_not_recognised() -> None:
    """Without the signature, "I am halfway into signing in as the administrator" is a cookie
    anybody can set from their own console."""
    client = _asking(_settings())
    client.cookies.set(COOKIE, f"deadbeef.{uuid4()}")

    assert client.get("/waiting").json()["user"] is None


def test_a_note_sealed_with_another_key_is_not_recognised() -> None:
    client = _asking(_settings())
    elsewhere = _settings(secret_key=SecretStr("b" * 32))
    client.cookies.set(COOKIE, seal(elsewhere, {"user": str(uuid4())}))

    assert client.get("/waiting").json()["user"] is None


def test_a_note_left_overnight_is_not_recognised() -> None:
    """This note plus a stolen password is the account, so it must not sit in a browser."""
    settings = _settings()
    client = _asking(settings)
    long_ago = datetime.now(UTC).timestamp() - TTL_SECONDS - 1
    client.cookies.set(COOKIE, seal(settings, {"user": str(uuid4())}, now=long_ago))

    assert client.get("/waiting").json()["user"] is None


def test_the_note_is_short_lived_in_the_browser_as_well_as_in_the_signature() -> None:
    """Both, because they answer different people: `Max-Age` tidies up after an honest
    visitor, and the signed date refuses somebody replaying the value without a browser."""
    header = _asking(_settings()).post("/login").headers["set-cookie"].lower()

    assert f"max-age={TTL_SECONDS}" in header


def test_the_note_does_not_travel_on_a_cross_site_request() -> None:
    """`SameSite=Lax` is what protects the route that reads it: a forged cross-site POST
    arrives with nobody waiting, so there is nothing for it to finish signing in as."""
    header = _asking(_settings()).post("/login").headers["set-cookie"].lower()

    assert "samesite=lax" in header
    assert "httponly" in header


def test_the_note_says_who_and_nothing_else() -> None:
    """Not the role, not the address, not what the password was: the route that reads it looks
    the account up itself, and a value the browser holds is a value somebody may read."""
    client = _asking(_settings())
    client.post("/login")
    value = client.cookies[COOKIE]

    body = value.split(".", 1)[1]
    assert "person@example.am" not in body
    assert "moderator" not in body


@pytest.mark.parametrize("env", ["local", "production"])
def test_the_note_is_marked_secure_wherever_the_platform_can_be(env: str) -> None:
    """Outside local the whole platform is https, and a note that opens an account must not
    be one a plain-http page can be made to leak."""
    header = _asking(_settings(app_env=env)).post("/login").headers["set-cookie"].lower()

    assert ("secure" in header) is (env != "local")
