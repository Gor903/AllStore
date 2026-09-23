"""The loop: a question in, an answer built only from real products out.

The shape is the one docs/rag-first.md, раздел 19 asks for — the model decides *what to look
for*, the catalogue decides *what exists*, and the answer is assembled from the second. The
model never hands us a product; it hands us a search, and we run it.

The loop yields as it goes rather than returning at the end. Search takes a third of a second
and the model takes twenty, so a visitor who waits for both sees nothing for twenty seconds
while the thing they asked for has been sitting ready the whole time.
"""

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.logging import get_logger
from app.models import Product
from app.services.assistant import tools
from app.services.assistant.client import AssistantUnavailableError, ChatModel, Reply
from app.services.assistant.prompt import SYSTEM_PROMPT

logger = get_logger(__name__)

FOUND_BUT_SILENT = "Вот что нашлось в каталоге по вашему запросу."


@dataclass
class Found:
    """Products the search turned up, sent before the model has written a word about them."""

    products: list[Product]


@dataclass
class Said:
    text: str


Event = Found | Said


@dataclass
class Answer:
    text: str
    # every product the assistant actually looked at, in the order it first met them
    products: list[Product] = field(default_factory=list)


async def stream(
    session: AsyncSession,
    settings: Settings,
    model: ChatModel,
    question: str,
    history: list[dict[str, str]] | None = None,
) -> AsyncIterator[Event]:
    messages: list[dict[str, Any]] = [{"role": "system", "content": SYSTEM_PROMPT}]
    for turn in history or []:
        messages.append({"role": turn["role"], "content": turn["content"]})
    messages.append({"role": "user", "content": question})

    seen: dict[str, Product] = {}
    for _ in range(settings.assistant_max_tool_rounds):
        reply = await model.reply(messages, tools.DEFINITIONS)
        if not reply.tool_calls:
            yield _said(reply.text.strip(), seen)
            return

        messages.append(_assistant_turn(reply))
        fresh: list[Product] = []
        for call in reply.tool_calls:
            note, found = await tools.run(session, settings, call.name, call.arguments)
            for product in found:
                if str(product.id) not in seen:
                    seen[str(product.id)] = product
                    fresh.append(product)
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call.id,
                    "content": note
                    or json.dumps(
                        [tools.describe(product) for product in found], ensure_ascii=False
                    ),
                }
            )
        if fresh:
            yield Found(fresh)

    # the rounds ran out: a small model can keep searching forever, and a visitor waiting on
    # that is worse served than one shown what the search already turned up
    logger.info("ассистент исчерпал круги поиска на вопросе: %s", question[:80])
    yield _said("", seen)


async def ask(
    session: AsyncSession,
    settings: Settings,
    model: ChatModel,
    question: str,
    history: list[dict[str, str]] | None = None,
) -> Answer:
    """The same conversation collected into one answer, for callers that cannot stream."""
    answer = Answer(text="")
    async for event in stream(session, settings, model, question, history):
        if isinstance(event, Found):
            answer.products.extend(event.products)
        else:
            answer.text = event.text
    return answer


def _said(text: str, seen: dict[str, Product]) -> Said:
    """A small model sometimes falls silent; silence is not an answer.

    With products in hand the visitor is served by the cards plus a line that states nothing
    beyond them. With neither text nor products there is nothing to serve, and saying so
    honestly beats an empty screen.
    """
    if text:
        return Said(text)
    if seen:
        return Said(FOUND_BUT_SILENT)
    logger.info("модель ответила пустотой и ничего не нашла")
    raise AssistantUnavailableError("пустой ответ модели")


def _assistant_turn(reply: Reply) -> dict[str, Any]:
    return {
        "role": "assistant",
        "content": reply.text,
        "tool_calls": [
            {
                "id": call.id,
                "type": "function",
                "function": {
                    "name": call.name,
                    "arguments": json.dumps(call.arguments, ensure_ascii=False),
                },
            }
            for call in reply.tool_calls
        ],
    }
