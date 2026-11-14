"""The two tools the assistant is given, and what they are allowed to return.

Two rather than one, because the decision "these are words to match" against "this is a
description of a thing" is exactly what a model is good at and a rule is bad at. Both run
through the catalogue the site itself is built on, so a product the assistant mentions is a
product a visitor can open.

Every character the model reads is paid for twice: it reads the whole search result back
before it writes a word, and on a CPU that reading is the slowest part of an answer. Measured
on the stand, eight full cards cost about 2500 characters and some forty seconds of the model
merely looking at them — so a product arrives with enough to talk about and nothing else.

An unknown tool or an empty argument is answered rather than raised: the model is a caller
like any other, and a refusal it can read beats an exception it cannot.
"""

import uuid
from decimal import Decimal
from typing import Any

import pytest

from app.core.config import get_settings
from app.models import Business, Category, Product, ProductAvailability
from app.services import catalog as catalog_service
from app.services.assistant import tools


def _product(**overrides: Any) -> Product:
    fields: dict[str, Any] = {
        "id": uuid.uuid4(),
        "name": "Чашка",
        "description": None,
        "price": Decimal("1500.00"),
        "currency": "AMD",
        "availability_status": ProductAvailability.IN_STOCK,
    }
    product = Product(**{**fields, **overrides})
    product.category = Category(name="Посуда", slug="dishes")
    product.business = Business(display_name="Ромашка", legal_name="ООО Ромашка")
    return product


class _Page:
    def __init__(self, items: list[Product]) -> None:
        self.items = items


def test_the_model_is_offered_both_searches_and_nothing_else() -> None:
    names = [definition["function"]["name"] for definition in tools.DEFINITIONS]

    assert names == [tools.EXACT_SEARCH, tools.SEMANTIC_SEARCH]


def test_each_tool_says_when_it_is_the_right_one() -> None:
    """The description is the whole instruction the model gets about choosing, so it has to
    name the case rather than the mechanism."""
    exact, semantic = (definition["function"] for definition in tools.DEFINITIONS)

    assert "буквально" in exact["description"]
    assert "своими" in semantic["description"]


def test_only_the_exact_search_takes_a_category() -> None:
    """Semantic search over one category is a narrower search over a smaller set, which is
    the opposite of what it is for."""
    exact, semantic = (definition["function"] for definition in tools.DEFINITIONS)

    assert set(exact["parameters"]["properties"]) == {"query", "category"}
    assert set(semantic["parameters"]["properties"]) == {"query"}
    assert exact["parameters"]["required"] == ["query"]


def test_a_product_arrives_with_enough_to_talk_about() -> None:
    described = tools.describe(_product(description="Фарфор ручной работы"))

    assert described == {
        "name": "Чашка",
        "price": "1500 AMD",
        "in_stock": True,
        "category": "Посуда",
        "shop": "Ромашка",
        "description": "Фарфор ручной работы",
    }


def test_and_with_nothing_the_visitor_could_not_see() -> None:
    """No identifier and no subdomain: the cards are assembled in code from the same products,
    so a UUID in here would cost the model a line of reading and buy the visitor nothing."""
    described = tools.describe(_product())

    assert "id" not in described
    assert "subdomain" not in described


def test_a_long_description_is_cut_where_the_model_stops_needing_it() -> None:
    described = tools.describe(_product(description="ч" * 500))

    assert described["description"] is not None
    assert len(described["description"]) == tools.DESCRIPTION_LIMIT + 1  # the ellipsis
    assert described["description"].endswith("…")


def test_a_product_with_nothing_said_about_it_says_nothing() -> None:
    """`None` rather than an empty string: a field that is there and empty invites the model
    to fill it."""
    assert tools.describe(_product(description="   "))["description"] is None


def test_a_price_is_given_without_the_pennies_nobody_reads_aloud() -> None:
    assert tools.describe(_product(price=Decimal("1500.49")))["price"] == "1500 AMD"


async def test_an_empty_query_is_answered_rather_than_searched(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called = False

    async def _never(*args: Any, **kwargs: Any) -> _Page:
        nonlocal called
        called = True
        return _Page([])

    monkeypatch.setattr(catalog_service, "list_products", _never)

    answer, products = await tools.run(None, get_settings(), tools.EXACT_SEARCH, {"query": "  "})  # type: ignore[arg-type]

    assert "нечего искать" in answer
    assert products == []
    assert called is False


async def test_a_tool_nobody_defined_is_answered_with_the_ones_that_exist(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    answer, products = await tools.run(
        None,  # type: ignore[arg-type]
        get_settings(),
        "delete_everything",
        {"query": "ваза"},
    )

    assert tools.EXACT_SEARCH in answer
    assert tools.SEMANTIC_SEARCH in answer
    assert products == []


async def test_the_exact_search_passes_the_category_the_customer_named(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asked: dict[str, Any] = {}

    async def _list(session: Any, **kwargs: Any) -> _Page:
        asked.update(kwargs)
        return _Page([_product()])

    monkeypatch.setattr(catalog_service, "list_products", _list)

    answer, products = await tools.run(
        None,  # type: ignore[arg-type]
        get_settings(),
        tools.EXACT_SEARCH,
        {"query": "чашка", "category": "dishes"},
    )

    assert asked["category_slug"] == "dishes"
    assert asked["limit"] == tools.MAX_RESULTS
    assert "settings" not in asked, "exact search does not go through the semantic service"
    assert answer == ""
    assert len(products) == 1


async def test_the_semantic_search_goes_through_the_service_that_knows_meanings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asked: dict[str, Any] = {}

    async def _list(session: Any, **kwargs: Any) -> _Page:
        asked.update(kwargs)
        return _Page([_product()])

    monkeypatch.setattr(catalog_service, "list_products", _list)

    await tools.run(
        None,  # type: ignore[arg-type]
        get_settings(),
        tools.SEMANTIC_SEARCH,
        {"query": "подарок на новоселье", "category": "dishes"},
    )

    assert asked["settings"] is not None
    assert asked["category_slug"] is None, "a category would narrow the one search that must not"


async def test_a_search_that_found_nothing_says_so_in_words(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _list(session: Any, **kwargs: Any) -> _Page:
        return _Page([])

    monkeypatch.setattr(catalog_service, "list_products", _list)

    answer, products = await tools.run(
        None,  # type: ignore[arg-type]
        get_settings(),
        tools.EXACT_SEARCH,
        {"query": "ваза"},
    )

    assert answer == "Ничего не нашлось."
    assert products == []


def test_the_cards_are_addressed_by_the_products_the_search_returned() -> None:
    """Never parsed out of what the model wrote: what it says and what the catalogue holds
    must not be able to disagree."""
    products = [_product(), _product()]

    assert tools.product_ids(products) == [product.id for product in products]
