"""Talking to a chat model that can call tools.

Deliberately not a vendor SDK: the wire format is the OpenAI-compatible
`/v1/chat/completions`, which a local Ollama speaks as readily as a hosted provider. Changing
where the assistant thinks is then a URL and a model name, not a rewrite.

Which makes the wire format the thing to test. Arguments arrive as a JSON string from some
servers and as an object from others, and a model that writes broken JSON has not asked for
anything we can run — dropping that call is the difference between an assistant that answers
without a search and one that raises in the middle of a stream.
"""

import json
from typing import Any

import httpx
import pytest
from pydantic import SecretStr

from app.core.config import Settings, get_settings
from app.services.assistant.client import (
    AssistantUnavailableError,
    OpenAICompatibleModel,
    build_model,
)


def _settings(**overrides: Any) -> Settings:
    return get_settings().model_copy(
        update={
            "assistant_base_url": "http://ollama:11434/v1",
            "assistant_model": "qwen2.5:3b",
            "assistant_api_key": None,
            **overrides,
        }
    )


def _answering(handler: Any) -> type[httpx.AsyncClient]:
    class Stub(httpx.AsyncClient):
        def __init__(self, **kwargs: Any) -> None:
            super().__init__(transport=httpx.MockTransport(handler))

    return Stub


def _message(**message: Any) -> httpx.Response:
    return httpx.Response(200, json={"choices": [{"message": message}]})


async def test_the_model_is_asked_at_the_endpoint_every_provider_speaks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asked: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        asked.append(request)
        return _message(content="Вот что нашлось")

    monkeypatch.setattr(httpx, "AsyncClient", _answering(handler))

    await build_model(_settings()).reply([{"role": "user", "content": "ваза"}], [])

    assert str(asked[0].url) == "http://ollama:11434/v1/chat/completions"
    body = json.loads(asked[0].content)
    assert body["model"] == "qwen2.5:3b"
    assert body["stream"] is False


async def test_a_key_travels_only_when_there_is_one(monkeypatch: pytest.MonkeyPatch) -> None:
    """The stand needs no account and no key; a hosted provider needs one. Sending an empty
    bearer would be refused by the second and ignored by the first, so neither is sent."""
    asked: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        asked.append(request)
        return _message(content="")

    monkeypatch.setattr(httpx, "AsyncClient", _answering(handler))

    await build_model(_settings()).reply([], [])
    await build_model(_settings(assistant_api_key=SecretStr("k"))).reply([], [])

    assert "authorization" not in asked[0].headers
    assert asked[1].headers["authorization"] == "Bearer k"


async def test_what_the_model_said_comes_back(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        httpx, "AsyncClient", _answering(lambda request: _message(content="Вот что нашлось"))
    )

    reply = await build_model(_settings()).reply([], [])

    assert reply.text == "Вот что нашлось"
    assert reply.tool_calls == []


async def test_a_turn_with_nothing_to_say_is_an_empty_string(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Some servers send `"content": null` when the turn is only a tool call."""
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        _answering(
            lambda request: _message(
                content=None,
                tool_calls=[
                    {"id": "1", "function": {"name": "exact_search", "arguments": {"q": "ваза"}}}
                ],
            )
        ),
    )

    reply = await build_model(_settings()).reply([], [])

    assert reply.text == ""
    assert reply.tool_calls[0].name == "exact_search"


async def test_arguments_are_read_whichever_way_the_server_sends_them(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        _answering(
            lambda request: _message(
                tool_calls=[
                    {"id": "a", "function": {"name": "one", "arguments": '{"q": "ваза"}'}},
                    {"id": "b", "function": {"name": "two", "arguments": {"q": "плед"}}},
                ]
            )
        ),
    )

    reply = await build_model(_settings()).reply([], [])

    assert [call.arguments for call in reply.tool_calls] == [{"q": "ваза"}, {"q": "плед"}]


async def test_a_call_nobody_could_run_is_dropped_rather_than_raised(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A model that wrote broken JSON has not asked for anything we can run; the turn still
    has whatever else it said in it."""
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        _answering(
            lambda request: _message(
                content="сейчас посмотрю",
                tool_calls=[
                    {"id": "a", "function": {"name": "one", "arguments": "{не json"}},
                    {"id": "b", "function": {"name": "two", "arguments": "[1, 2]"}},
                    {"id": "c", "function": {"name": "three", "arguments": {"q": "ваза"}}},
                ],
            )
        ),
    )

    reply = await build_model(_settings()).reply([], [])

    assert [call.name for call in reply.tool_calls] == ["three"]
    assert reply.text == "сейчас посмотрю"


async def test_a_call_with_no_identifier_gets_its_position(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The identifier is what the answer to a tool call is addressed to, so it cannot be
    empty — and some servers do not send one."""
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        _answering(
            lambda request: _message(tool_calls=[{"function": {"name": "one", "arguments": {}}}])
        ),
    )

    reply = await build_model(_settings()).reply([], [])

    assert reply.tool_calls[0].id == "0"


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(500),
        httpx.Response(200, text="не json"),
        httpx.Response(200, json={"choices": []}),
        httpx.Response(200, json={}),
    ],
)
async def test_a_model_that_answered_nothing_useful_is_unavailable(
    monkeypatch: pytest.MonkeyPatch, response: httpx.Response
) -> None:
    """One exception for every way of not getting an answer: the caller turns it into an
    honest sentence rather than guessing what went wrong."""
    monkeypatch.setattr(httpx, "AsyncClient", _answering(lambda request: response))

    with pytest.raises(AssistantUnavailableError):
        await build_model(_settings()).reply([], [])


def test_an_assistant_with_nowhere_to_think_says_so_at_once() -> None:
    """Rather than at the first question, which would be a 500 on a page that works."""
    with pytest.raises(AssistantUnavailableError, match="ASSISTANT_BASE_URL"):
        OpenAICompatibleModel(_settings(assistant_base_url=None))
