"""The loop: a question in, an answer built only from real products out.

The model decides *what to look for*, the catalogue decides *what exists*, and the answer is
assembled from the second. The model never hands us a product; it hands us a search, and we
run it — which is why nothing it writes can put a product on the screen.

The loop yields as it goes rather than returning at the end. The search takes a third of a
second and the model takes twenty, so a visitor who waits for both sees nothing for twenty
seconds while the thing they asked for has been sitting ready the whole time.

Two failures are deliberate shapes rather than accidents. A small model sometimes falls
silent: with products in hand the cards plus one line that states nothing beyond them serve
the visitor, and with neither text nor products there is nothing to serve and saying so
honestly beats an empty screen. And the rounds are bounded, because a small model can keep
searching forever.
"""

import json
import uuid
from decimal import Decimal
from typing import Any

import pytest

from app.core.config import Settings, get_settings
from app.models import Business, Category, Product, ProductAvailability
from app.services.assistant import conversation, tools
from app.services.assistant.client import AssistantUnavailableError, Reply, ToolCall
from app.services.assistant.prompt import SYSTEM_PROMPT


def _product(name: str = "Чашка") -> Product:
    product = Product(
        id=uuid.uuid4(),
        name=name,
        description=None,
        price=Decimal("1500.00"),
        currency="AMD",
        availability_status=ProductAvailability.IN_STOCK,
    )
    product.category = Category(name="Посуда", slug="dishes")
    product.business = Business(display_name="Ромашка", legal_name="ООО Ромашка")
    return product


class _Model:
    """Answers with the replies it was given, in order, and remembers what it was asked."""

    def __init__(self, *replies: Reply) -> None:
        self._replies = list(replies)
        self.asked: list[list[dict[str, Any]]] = []

    async def reply(self, messages: list[dict[str, Any]], _tools: list[dict[str, Any]]) -> Reply:
        self.asked.append([dict(message) for message in messages])
        return self._replies.pop(0) if self._replies else Reply(text="")


def _searching(monkeypatch: pytest.MonkeyPatch, *results: list[Product]) -> list[str]:
    """Stands in for the catalogue: one answer per call, in order."""
    queries: list[str] = []
    answers = list(results)

    async def _run(
        session: Any, settings: Settings, name: str, arguments: dict[str, Any]
    ) -> tuple[str, list[Product]]:
        queries.append(str(arguments.get("query", "")))
        found = answers.pop(0) if answers else []
        return ("" if found else "Ничего не нашлось."), found

    monkeypatch.setattr(tools, "run", _run)
    return queries


def _settings(**overrides: Any) -> Settings:
    return get_settings().model_copy(update={"assistant_max_tool_rounds": 4, **overrides})


async def _collect(stream: Any) -> list[Any]:
    return [event async for event in stream]


async def test_a_model_that_asks_for_nothing_is_simply_answered(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _searching(monkeypatch)
    model = _Model(Reply(text="Ничем не могу помочь"))

    events = await _collect(conversation.stream(None, _settings(), model, "привет"))  # type: ignore[arg-type]

    assert [event.text for event in events] == ["Ничем не могу помочь"]


async def test_the_question_arrives_after_the_rules_and_the_history(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _searching(monkeypatch)
    model = _Model(Reply(text="ответ"))

    await _collect(
        conversation.stream(
            None,  # type: ignore[arg-type]
            _settings(),
            model,
            "ваза",
            [
                {"role": "user", "content": "привет"},
                {"role": "assistant", "content": "здравствуйте"},
            ],
        )
    )

    roles = [message["role"] for message in model.asked[0]]
    assert roles == ["system", "user", "assistant", "user"]
    assert model.asked[0][0]["content"] == SYSTEM_PROMPT
    assert model.asked[0][-1]["content"] == "ваза"


async def test_the_cards_are_sent_before_the_model_has_written_a_word(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Which is the whole point of streaming here: the search is ready in a third of a second
    and the sentence about it takes twenty."""
    found = [_product()]
    _searching(monkeypatch, found)
    model = _Model(
        Reply(tool_calls=[ToolCall(id="1", name=tools.EXACT_SEARCH, arguments={"query": "ваза"})]),
        Reply(text="Вот что нашлось"),
    )

    events = await _collect(conversation.stream(None, _settings(), model, "ваза"))  # type: ignore[arg-type]

    assert isinstance(events[0], conversation.Found)
    assert events[0].products == found
    assert isinstance(events[1], conversation.Said)


async def test_what_the_search_returned_is_handed_back_to_the_model_as_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _searching(monkeypatch, [_product()])
    model = _Model(
        Reply(tool_calls=[ToolCall(id="7", name=tools.EXACT_SEARCH, arguments={"query": "ваза"})]),
        Reply(text="Вот что нашлось"),
    )

    await _collect(conversation.stream(None, _settings(), model, "ваза"))  # type: ignore[arg-type]

    tool_turn = model.asked[1][-1]
    assert tool_turn["role"] == "tool"
    assert tool_turn["tool_call_id"] == "7"
    assert "Чашка" in tool_turn["content"]


async def test_the_model_s_own_turn_is_replayed_with_its_call_in_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A tool answer with no call before it is a conversation the server refuses."""
    _searching(monkeypatch, [_product()])
    model = _Model(
        Reply(tool_calls=[ToolCall(id="7", name=tools.EXACT_SEARCH, arguments={"query": "ваза"})]),
        Reply(text="ответ"),
    )

    await _collect(conversation.stream(None, _settings(), model, "ваза"))  # type: ignore[arg-type]

    assistant_turn = model.asked[1][-2]
    assert assistant_turn["role"] == "assistant"
    assert json.loads(assistant_turn["tool_calls"][0]["function"]["arguments"]) == {"query": "ваза"}


async def test_a_product_met_twice_is_shown_once(monkeypatch: pytest.MonkeyPatch) -> None:
    """Two searches often overlap, and the same card twice reads as two products."""
    cup = _product()
    _searching(monkeypatch, [cup], [cup, _product("Блюдце")])
    model = _Model(
        Reply(tool_calls=[ToolCall(id="1", name=tools.EXACT_SEARCH, arguments={"query": "ваза"})]),
        Reply(
            tool_calls=[ToolCall(id="2", name=tools.SEMANTIC_SEARCH, arguments={"query": "посуда"})]
        ),
        Reply(text="ответ"),
    )

    events = await _collect(conversation.stream(None, _settings(), model, "ваза"))  # type: ignore[arg-type]

    shown = [
        product.name
        for event in events
        if isinstance(event, conversation.Found)
        for product in event.products
    ]
    assert shown == ["Чашка", "Блюдце"]


async def test_a_search_that_found_nothing_yields_no_cards(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _searching(monkeypatch, [])
    model = _Model(
        Reply(tool_calls=[ToolCall(id="1", name=tools.EXACT_SEARCH, arguments={"query": "ваза"})]),
        Reply(text="Ничего не нашлось"),
    )

    events = await _collect(conversation.stream(None, _settings(), model, "ваза"))  # type: ignore[arg-type]

    assert all(isinstance(event, conversation.Said) for event in events)


async def test_a_model_that_falls_silent_with_products_still_serves_the_visitor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One line that states nothing beyond the cards — because the cards are the answer."""
    _searching(monkeypatch, [_product()])
    model = _Model(
        Reply(tool_calls=[ToolCall(id="1", name=tools.EXACT_SEARCH, arguments={"query": "ваза"})]),
        Reply(text="   "),
    )

    events = await _collect(conversation.stream(None, _settings(), model, "ваза"))  # type: ignore[arg-type]

    assert events[-1].text == conversation.FOUND_BUT_SILENT


async def test_a_model_that_falls_silent_with_nothing_found_is_a_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Saying so honestly beats an empty screen that looks like a page that broke."""
    _searching(monkeypatch)
    model = _Model(Reply(text=""))

    with pytest.raises(AssistantUnavailableError):
        await _collect(conversation.stream(None, _settings(), model, "ваза"))  # type: ignore[arg-type]


async def test_the_rounds_are_bounded_and_what_was_found_is_still_shown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A small model can keep searching forever, and a visitor waiting on that is worse served
    than one shown what the search already turned up."""
    _searching(monkeypatch, [_product()], [], [], [])
    searching = Reply(
        tool_calls=[ToolCall(id="1", name=tools.EXACT_SEARCH, arguments={"query": "ваза"})]
    )
    model = _Model(searching, searching, searching, searching, searching)

    bounded = _settings(assistant_max_tool_rounds=3)
    events = await _collect(conversation.stream(None, bounded, model, "ваза"))  # type: ignore[arg-type]

    assert len(model.asked) == 3
    assert events[-1].text == conversation.FOUND_BUT_SILENT


async def test_the_whole_conversation_can_be_collected_for_a_caller_that_cannot_stream(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _searching(monkeypatch, [_product()])
    model = _Model(
        Reply(tool_calls=[ToolCall(id="1", name=tools.EXACT_SEARCH, arguments={"query": "ваза"})]),
        Reply(text="Вот что нашлось"),
    )

    answer = await conversation.ask(None, _settings(), model, "ваза")  # type: ignore[arg-type]

    assert answer.text == "Вот что нашлось"
    assert [product.name for product in answer.products] == ["Чашка"]
