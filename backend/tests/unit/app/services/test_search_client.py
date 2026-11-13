"""The one place backend talks to the search service.

The whole module is a promise: nothing here raises. Semantic search is an addition to the
catalogue rather than a part of it (ADR 10), and when the service is missing, slow or broken
the catalogue has to answer exactly as it did before semantic search existed. An empty list is
the answer both to "found nothing" and to "could not be reached", because the caller does the
same thing either way — it shows what the words already found.

So what is tested here is not the happy path. It is every unhappy one.
"""

import uuid
from typing import Any

import httpx
import pytest

from app.core.config import Settings, get_settings
from app.services import search_client

PRODUCT = uuid.uuid4()


def _settings(**overrides: Any) -> Settings:
    """The address is set explicitly: the test environment leaves it empty, and without this
    the module would return on its first line — the test would pass without reaching what it
    claims to check."""
    return get_settings().model_copy(
        update={"search_service_url": "http://search:8000", **overrides}
    )


def _answering(handler: Any) -> type[httpx.AsyncClient]:
    """Replaces the client entirely, so the test does not depend on a network."""

    class Stub(httpx.AsyncClient):
        def __init__(self, **kwargs: Any) -> None:
            super().__init__(transport=httpx.MockTransport(handler))

    return Stub


async def test_without_a_service_nothing_is_asked(monkeypatch: pytest.MonkeyPatch) -> None:
    """An empty `SEARCH_SERVICE_URL` means "there is no search", not "the search is broken":
    no request is made at all."""
    asked = False

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal asked
        asked = True
        return httpx.Response(200, json={"matches": []})

    monkeypatch.setattr(httpx, "AsyncClient", _answering(handler))

    assert await search_client.semantic_ids(_settings(search_service_url=None), "ваза", 10) == []
    assert asked is False


async def test_matches_come_back_in_the_order_the_service_gave(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The order is the answer: the service returned them by closeness, and reordering them
    here would throw away the only thing it knows that we do not."""
    first, second = uuid.uuid4(), uuid.uuid4()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"matches": [{"product_id": str(first)}, {"product_id": str(second)}]}
        )

    monkeypatch.setattr(httpx, "AsyncClient", _answering(handler))

    found = await search_client.semantic_ids(_settings(), "сосуд для букета", 10)

    assert found == [first, second]


@pytest.mark.parametrize(
    ("name", "response"),
    [
        ("five hundred", httpx.Response(500)),
        ("not json", httpx.Response(200, text="not json at all")),
        ("no matches key", httpx.Response(200, json={"items": []})),
        ("a match without product_id", httpx.Response(200, json={"matches": [{"score": 0.9}]})),
        (
            "product_id is not a uuid",
            httpx.Response(200, json={"matches": [{"product_id": "ваза"}]}),
        ),
    ],
)
async def test_a_broken_answer_leaves_the_catalogue_as_it_was(
    monkeypatch: pytest.MonkeyPatch, name: str, response: httpx.Response
) -> None:
    """Any broken answer is an empty list rather than an exception. The last two are about the
    answer being read inside the try, like the request: a service that returns rubbish in a
    field must not take the catalogue page down with it."""
    monkeypatch.setattr(httpx, "AsyncClient", _answering(lambda request: response))

    assert await search_client.semantic_ids(_settings(), "ваза", 10) == []


async def test_a_timeout_is_an_empty_answer(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("too slow", request=request)

    monkeypatch.setattr(httpx, "AsyncClient", _answering(handler))

    assert await search_client.semantic_ids(_settings(), "ваза", 10) == []


async def test_the_address_tolerates_a_trailing_slash(monkeypatch: pytest.MonkeyPatch) -> None:
    """The address comes from an environment variable, and a person writes those."""
    asked: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        asked.append(str(request.url))
        return httpx.Response(200, json={"matches": []})

    monkeypatch.setattr(httpx, "AsyncClient", _answering(handler))

    await search_client.semantic_ids(_settings(search_service_url="http://search:8000/"), "ваза", 1)

    assert asked == ["http://search:8000/search"]


async def test_a_hint_about_a_changed_product_is_sent_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asked: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        asked.append(str(request.url))
        return httpx.Response(200)

    monkeypatch.setattr(httpx, "AsyncClient", _answering(handler))

    await search_client.product_changed(_settings(), PRODUCT)

    assert asked == [f"http://search:8000/reindex?product_id={PRODUCT}"]


async def test_a_hint_that_did_not_arrive_is_forgotten(monkeypatch: pytest.MonkeyPatch) -> None:
    """A hint rather than a command: the service sweeps the catalogue on its own and would
    notice the change within minutes anyway."""

    asked: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        asked.append(str(request.url))
        return httpx.Response(503)

    monkeypatch.setattr(httpx, "AsyncClient", _answering(handler))

    await search_client.product_changed(_settings(), PRODUCT)

    assert asked, "the hint was sent; its refusal is what has to be swallowed"
