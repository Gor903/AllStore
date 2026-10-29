"""Asking whether a password is already on a list attackers try first.

Two properties matter more than the lookup itself. The password must not leave — only five
characters of its hash do, which is why this is a range query and not a question about one
password. And an outage somewhere else must not stop anybody signing up, which is why every
failure answers "no".
"""

import hashlib
from typing import Any, ClassVar, Self

import httpx
import pytest

from app.core.config import Settings, get_settings
from app.services.breached_passwords import is_known_leaked

LEAKED = "correct horse battery staple"
URL = "https://leaks.example/range"


def _settings(**overrides: object) -> Settings:
    return get_settings().model_copy(update=overrides)


def _digest(password: str) -> str:
    return hashlib.sha1(password.encode(), usedforsecurity=False).hexdigest().upper()


class _Answering:
    """Stands in for the http client, and records what it was asked for."""

    asked: ClassVar[list[str]] = []

    def __init__(self, body: str = "", status: int = 200) -> None:
        self._body = body
        self._status = status

    def __call__(self, **_: Any) -> Self:
        return self

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *_: object) -> None:
        return None

    async def get(self, url: str) -> httpx.Response:
        type(self).asked.append(url)
        if self._status >= 400:
            raise httpx.HTTPStatusError(
                "nope", request=httpx.Request("GET", url), response=httpx.Response(self._status)
            )
        # a Response built by hand has no request attached, and `raise_for_status` insists
        # on one — the service calls it, so the stand-in has to hand back a whole answer
        return httpx.Response(self._status, text=self._body, request=httpx.Request("GET", url))


@pytest.fixture
def answering(monkeypatch: pytest.MonkeyPatch) -> Any:
    _Answering.asked = []

    def install(body: str = "", status: int = 200) -> None:
        monkeypatch.setattr(httpx, "AsyncClient", _Answering(body, status))

    return install


async def test_a_password_on_the_list_is_recognised(answering: Any) -> None:
    answering(f"0000000000000000000000000000000000:1\r\n{_digest(LEAKED)[5:]}:42")

    assert await is_known_leaked(_settings(breached_password_url=URL), LEAKED) is True


async def test_a_password_nobody_has_seen_passes(answering: Any) -> None:
    answering("ABCDEF0123456789ABCDEF0123456789ABC:1")

    assert await is_known_leaked(_settings(breached_password_url=URL), LEAKED) is False


async def test_only_five_characters_of_the_hash_travel(answering: Any) -> None:
    """The point of the whole arrangement. Anybody watching the request learns that somebody
    checked a password whose hash starts with five known characters, which is roughly nothing."""
    answering("")

    await is_known_leaked(_settings(breached_password_url=URL), LEAKED)

    asked = _Answering.asked[0]
    assert asked.endswith(_digest(LEAKED)[:5])
    assert _digest(LEAKED)[5:] not in asked
    assert LEAKED not in asked


async def test_an_outage_elsewhere_does_not_stop_anybody(answering: Any) -> None:
    """A check that can lock everybody out of registering is a worse problem than the one it
    solves. The password is advice; argon2 and the rate limits are the protection."""
    answering("", status=503)

    assert await is_known_leaked(_settings(breached_password_url=URL), LEAKED) is False


async def test_with_no_service_configured_nothing_is_asked(answering: Any) -> None:
    answering("")

    assert await is_known_leaked(_settings(breached_password_url=None), LEAKED) is False
    assert _Answering.asked == []
