"""The assistant, with a scripted model in place of a real one.

What is checked is not whether a model is clever — that is judged by hand on the stand — but
the shape of the loop around it: that the products a visitor sees come from the catalogue and
not from the text, that a model which never stops searching is stopped, and that a broken
answer degrades into an honest one rather than an exception.
"""

import json
from typing import Any

import pytest
from httpx import AsyncClient, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.services.assistant import conversation
from app.services.assistant.client import AssistantUnavailableError, Reply, ToolCall
from app.services.assistant.tools import EXACT_SEARCH, SEMANTIC_SEARCH
from tests.integration.conftest import csrf_headers
from tests.integration.test_catalog import (
    PRODUCT_MODERATION,
    a_live_shop,
    a_published_product,
    anonymous,
    switch,
)

pytestmark = pytest.mark.integration

ASK = "/api/v1/assistant/ask"


class ScriptedModel:
    """Answers with whatever the test put in the script, in order."""

    def __init__(self, *replies: Reply) -> None:
        self._replies = list(replies)
        self.seen: list[list[dict[str, Any]]] = []

    async def reply(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> Reply:
        self.seen.append(messages)
        if not self._replies:
            return Reply(text="Больше сказать нечего.")
        return self._replies.pop(0)


def searching(name: str, query: str) -> Reply:
    return Reply(tool_calls=[ToolCall(id="1", name=name, arguments={"query": query})])


def lines(response: Response) -> list[dict[str, Any]]:
    """The answer travels as JSON lines, one per thing that became ready."""
    return [json.loads(line) for line in response.text.splitlines() if line]


@pytest.fixture
def configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "assistant_base_url", "http://ollama:11434/v1")


async def test_the_assistant_answers_about_products_it_searched_for(
    api_client: AsyncClient, session: AsyncSession, configured: None
) -> None:
    shop = await a_live_shop(api_client, session, "cups")
    vase = await a_published_product(api_client, session, shop, name="Ваза «Гюмри»")
    model = ScriptedModel(
        searching(EXACT_SEARCH, "ваза"),
        Reply(text="Нашёл вазу ручной работы."),
    )

    answer = await conversation.ask(session, get_settings(), model, "Есть керамические вазы?", None)

    assert answer.text == "Нашёл вазу ручной работы."
    assert [str(product.id) for product in answer.products] == [vase]


async def test_the_products_come_from_the_catalogue_not_from_the_text(
    api_client: AsyncClient, session: AsyncSession, configured: None
) -> None:
    """The model may write anything; only what the tools returned reaches the visitor."""
    shop = await a_live_shop(api_client, session, "cups")
    await a_published_product(api_client, session, shop, name="Ваза «Гюмри»")
    model = ScriptedModel(
        searching(EXACT_SEARCH, "ваза"),
        Reply(text="Ещё у нас есть ваза «Арарат» за 3000 драм и доставка за час."),
    )

    answer = await conversation.ask(session, get_settings(), model, "Что есть?", None)

    # the invented vase is in the text and nowhere else: the card list is what the shop holds
    assert [product.name for product in answer.products] == ["Ваза «Гюмри»"]


async def test_a_model_that_only_talks_is_answered_as_is(
    session: AsyncSession, configured: None
) -> None:
    model = ScriptedModel(Reply(text="Уточните, пожалуйста, что именно вы ищете."))

    answer = await conversation.ask(session, get_settings(), model, "Привет", None)

    assert answer.products == []
    assert "Уточните" in answer.text


async def test_a_model_that_never_stops_searching_and_finds_nothing_is_stopped(
    session: AsyncSession, configured: None
) -> None:
    """A small model can search forever; a visitor waiting on that is served worse than one told."""
    model = ScriptedModel(*[searching(SEMANTIC_SEARCH, "подарок") for _ in range(10)])

    with pytest.raises(AssistantUnavailableError):
        await conversation.ask(session, get_settings(), model, "Что подарить?", None)


async def test_a_model_that_never_stops_searching_still_shows_what_it_found(
    api_client: AsyncClient, session: AsyncSession, configured: None
) -> None:
    """Rounds run out, but the products are real: the cards are worth more than an apology."""
    shop = await a_live_shop(api_client, session, "cups")
    vase = await a_published_product(api_client, session, shop, name="Ваза «Гюмри»")
    model = ScriptedModel(*[searching(EXACT_SEARCH, "ваза") for _ in range(10)])

    answer = await conversation.ask(session, get_settings(), model, "Есть вазы?", None)

    assert [str(product.id) for product in answer.products] == [vase]
    assert answer.text == conversation.FOUND_BUT_SILENT


async def test_a_silent_model_with_products_still_answers(
    api_client: AsyncClient, session: AsyncSession, configured: None
) -> None:
    """A small model sometimes returns nothing at all; an empty screen is not an answer."""
    shop = await a_live_shop(api_client, session, "cups")
    vase = await a_published_product(api_client, session, shop, name="Ваза «Гюмри»")
    model = ScriptedModel(searching(EXACT_SEARCH, "ваза"), Reply(text="   "))

    answer = await conversation.ask(session, get_settings(), model, "Есть вазы?", None)

    # the line states nothing the tools did not return — the price and shop live on the cards
    assert answer.text == conversation.FOUND_BUT_SILENT
    assert [str(product.id) for product in answer.products] == [vase]


async def test_a_silent_model_with_nothing_found_is_not_an_answer(
    session: AsyncSession, configured: None
) -> None:
    model = ScriptedModel(Reply(text=""))

    with pytest.raises(AssistantUnavailableError):
        await conversation.ask(session, get_settings(), model, "Есть вазы?", None)


async def test_an_unknown_tool_is_answered_not_raised(
    session: AsyncSession, configured: None
) -> None:
    """The model is a caller like any other: a refusal it can read beats an exception."""
    model = ScriptedModel(
        Reply(tool_calls=[ToolCall(id="1", name="order_product", arguments={"query": "ваза"})]),
        Reply(text="Заказать я не могу, но могу поискать."),
    )

    answer = await conversation.ask(session, get_settings(), model, "Закажи вазу", None)

    assert "поискать" in answer.text


async def test_a_hidden_product_never_reaches_the_assistant(
    api_client: AsyncClient, session: AsyncSession, configured: None
) -> None:
    """Visibility is decided in one place, and the assistant is not that place."""
    shop = await a_live_shop(api_client, session, "cups")
    hidden = await a_published_product(api_client, session, shop, name="Ваза «Гюмри»")
    switch(api_client, shop.moderator)
    await api_client.post(f"{PRODUCT_MODERATION}/{hidden}/hide", headers=csrf_headers(api_client))
    model = ScriptedModel(searching(EXACT_SEARCH, "ваза"), Reply(text="Вот что есть."))

    answer = await conversation.ask(session, get_settings(), model, "Есть вазы?", None)

    assert answer.products == []


async def test_without_a_model_the_endpoint_says_so(api_client: AsyncClient) -> None:
    await anonymous(api_client)

    response = await api_client.post(ASK, json={"question": "Есть вазы?"})

    assert response.status_code == 503
    assert "помощник" in response.json()["error"]["message"].lower()


async def test_a_broken_model_does_not_break_the_answer(
    api_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The site is expected to survive its assistant, exactly as it survives its search."""
    monkeypatch.setattr(get_settings(), "assistant_base_url", "http://127.0.0.1:1/v1")
    await anonymous(api_client)

    response = await api_client.post(ASK, json={"question": "Есть вазы?"})

    # the stream opened before the model was reached, so the failure arrives as a line in it
    assert response.status_code == 200
    failure = lines(response)[-1]
    assert failure["type"] == "error"
    # the visitor is told what still works, not handed a stack trace
    assert "каталог" in failure["message"].lower()


async def test_the_products_arrive_before_the_text(
    api_client: AsyncClient, session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The whole point of the stream: the search is a third of a second, the model is twenty."""
    monkeypatch.setattr(get_settings(), "assistant_base_url", "http://ollama:11434/v1")
    shop = await a_live_shop(api_client, session, "cups")
    await a_published_product(api_client, session, shop, name="Ваза «Гюмри»")
    model = ScriptedModel(searching(EXACT_SEARCH, "ваза"), Reply(text="Нашёл вазу."))
    monkeypatch.setattr("app.api.assistant.build_model", lambda settings: model)
    await anonymous(api_client)

    response = await api_client.post(ASK, json={"question": "Есть вазы?"})

    kinds = [line["type"] for line in lines(response)]
    assert kinds == ["products", "answer"]
    first, last = lines(response)
    assert [product["name"] for product in first["products"]] == ["Ваза «Гюмри»"]
    assert last["text"] == "Нашёл вазу."


async def test_the_question_has_a_ceiling(api_client: AsyncClient, configured: None) -> None:
    await anonymous(api_client)

    response = await api_client.post(ASK, json={"question": "а" * 5000})

    assert response.status_code == 422


def test_a_tool_call_with_unreadable_arguments_is_dropped() -> None:
    """A model that writes broken JSON has not asked for anything we can run."""
    from app.services.assistant.client import _tool_calls

    calls = _tool_calls(
        {
            "tool_calls": [
                {"id": "1", "function": {"name": EXACT_SEARCH, "arguments": "{не json}"}},
                {"id": "2", "function": {"name": EXACT_SEARCH, "arguments": '{"query": "ваза"}'}},
            ]
        }
    )

    assert [call.id for call in calls] == ["2"]
    assert calls[0].arguments == {"query": "ваза"}
