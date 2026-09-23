"""Talking to a chat model that can call tools.

Deliberately not a vendor SDK: the wire format is the OpenAI-compatible
`/v1/chat/completions`, which a local Ollama speaks as readily as a hosted provider. Changing
where the assistant thinks is then a URL and a model name, not a rewrite — and the stand needs
no account, no key and no per-token bill to run it.
"""

import json
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx

from app.core.config import Settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class AssistantUnavailableError(Exception):
    """The model could not be reached. The caller turns this into an honest answer."""


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class Reply:
    """One turn of the model: either something to say, or tools to run, or both."""

    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)


class ChatModel(Protocol):
    async def reply(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> Reply: ...


class OpenAICompatibleModel:
    """Any endpoint that implements `/chat/completions` with tool calling."""

    def __init__(self, settings: Settings) -> None:
        if settings.assistant_base_url is None:
            raise AssistantUnavailableError("ASSISTANT_BASE_URL не задан")
        self._url = f"{settings.assistant_base_url.rstrip('/')}/chat/completions"
        self._model = settings.assistant_model
        self._timeout = settings.assistant_timeout_seconds
        self._max_tokens = settings.assistant_max_tokens
        key = settings.assistant_api_key
        self._headers = {"Authorization": f"Bearer {key.get_secret_value()}"} if key else {}

    async def reply(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> Reply:
        payload = {
            "model": self._model,
            "messages": messages,
            "tools": tools,
            "max_tokens": self._max_tokens,
            "stream": False,
        }
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(self._url, json=payload, headers=self._headers)
                response.raise_for_status()
                message = response.json()["choices"][0]["message"]
        except (httpx.HTTPError, KeyError, IndexError, ValueError) as error:
            logger.warning("модель ассистента недоступна", exc_info=True)
            raise AssistantUnavailableError(str(error)) from error
        return Reply(text=message.get("content") or "", tool_calls=_tool_calls(message))


def _tool_calls(message: dict[str, Any]) -> list[ToolCall]:
    """Arguments arrive as a JSON string from some servers and as an object from others."""
    calls = []
    for index, call in enumerate(message.get("tool_calls") or []):
        function = call.get("function", {})
        raw = function.get("arguments") or {}
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except ValueError:
                # a model that writes broken JSON has not asked for anything we can run
                logger.info("аргументы инструмента не разобрать: %s", raw)
                continue
        if not isinstance(raw, dict):
            continue
        calls.append(
            ToolCall(id=str(call.get("id") or index), name=function.get("name", ""), arguments=raw)
        )
    return calls


def build_model(settings: Settings) -> ChatModel:
    return OpenAICompatibleModel(settings)
