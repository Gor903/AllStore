"""The loop: a question in, an answer built only from real products out.

The shape is the one docs/rag-first.md, раздел 19 asks for — the model decides *what to look
for*, the catalogue decides *what exists*, and the answer is assembled from the second. The
model never hands us a product; it hands us a search, and we run it.
"""

import json
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


@dataclass
class Answer:
    text: str
    # every product the assistant actually looked at, in the order it first met them
    products: list[Product] = field(default_factory=list)


async def ask(
    session: AsyncSession,
    settings: Settings,
    model: ChatModel,
    question: str,
    history: list[dict[str, str]] | None = None,
) -> Answer:
    messages: list[dict[str, Any]] = [{"role": "system", "content": SYSTEM_PROMPT}]
    for turn in history or []:
        messages.append({"role": turn["role"], "content": turn["content"]})
    messages.append({"role": "user", "content": question})

    seen: dict[str, Product] = {}
    for _ in range(settings.assistant_max_tool_rounds):
        reply = await model.reply(messages, tools.DEFINITIONS)
        if not reply.tool_calls:
            return _answer(reply.text.strip(), list(seen.values()))

        messages.append(_assistant_turn(reply))
        for call in reply.tool_calls:
            note, found = await tools.run(session, settings, call.name, call.arguments)
            for product in found:
                seen.setdefault(str(product.id), product)
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

    # the rounds ran out: a small model can keep searching forever, and a visitor waiting on
    # that is worse served than one shown what the search already turned up
    logger.info("ассистент исчерпал круги поиска на вопросе: %s", question[:80])
    return _answer("", list(seen.values()))


FOUND_BUT_SILENT = "Вот что нашлось в каталоге по вашему запросу."


def _answer(text: str, products: list[Product]) -> Answer:
    """A small model sometimes falls silent; silence is not an answer.

    With products in hand the visitor is served by the cards plus a line that states nothing
    beyond them. With neither text nor products there is nothing to serve, and saying so
    honestly beats an empty screen.
    """
    if text:
        return Answer(text=text, products=products)
    if products:
        return Answer(text=FOUND_BUT_SILENT, products=products)
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
