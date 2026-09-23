"""The two tools the assistant is given, and what they are allowed to return.

Two rather than one, because the decision "these are words to match" against "this is a
description of a thing" is exactly what a model is good at and a rule is bad at
(docs/rag-first.md, раздел 26). Both run through the catalogue the site itself is built on, so
a product the assistant mentions is a product a visitor can open.
"""

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.models import Product
from app.services import catalog as catalog_service

# what fits in a model's context without drowning it: enough to answer, not the whole card
DESCRIPTION_LIMIT = 200
MAX_RESULTS = 8

EXACT_SEARCH = "exact_search"
SEMANTIC_SEARCH = "semantic_search"

DEFINITIONS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": EXACT_SEARCH,
            "description": (
                "Искать товары по словам, которые покупатель назвал буквально: название "
                "товара, название магазина. Подходит, когда в запросе есть конкретное слово "
                "из карточки товара."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Слова для поиска"},
                    "category": {
                        "type": "string",
                        "description": "Необязательно: slug категории, если покупатель её назвал",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": SEMANTIC_SEARCH,
            "description": (
                "Искать товары по смыслу запроса, когда покупатель описывает вещь своими "
                "словами, а не называет её: «что-то тёплое на зиму», «подарок на новоселье». "
                "Слова запроса могут не встречаться в карточке товара."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Описание того, что нужно покупателю",
                    }
                },
                "required": ["query"],
            },
        },
    },
]


def describe(product: Product) -> dict[str, Any]:
    """A product as the model sees it: enough to talk about, never enough to invent."""
    store = product.business.store
    description = (product.description or "").strip()
    if len(description) > DESCRIPTION_LIMIT:
        description = description[:DESCRIPTION_LIMIT].rstrip() + "…"
    return {
        "id": str(product.id),
        "name": product.name,
        "price": f"{product.price:.0f} {product.currency}",
        "in_stock": product.availability_status.value == "in_stock",
        "category": product.category.name,
        "shop": product.business.display_name,
        "shop_subdomain": store.subdomain if store is not None else None,
        "description": description or None,
    }


async def run(
    session: AsyncSession,
    settings: Settings,
    name: str,
    arguments: dict[str, Any],
) -> tuple[str, list[Product]]:
    """Executes one tool call. Returns what to tell the model and the products behind it.

    An unknown tool or a bad argument is answered, not raised: the model is a caller like any
    other, and a refusal it can read beats an exception it cannot.
    """
    query = str(arguments.get("query") or "").strip()
    if not query:
        return "Пустой запрос: нечего искать.", []
    category = arguments.get("category")
    if name == EXACT_SEARCH:
        page = await catalog_service.list_products(
            session,
            query=query,
            category_slug=str(category) if category else None,
            subdomain=None,
            limit=MAX_RESULTS,
            offset=0,
        )
    elif name == SEMANTIC_SEARCH:
        page = await catalog_service.list_products(
            session,
            query=query,
            category_slug=None,
            subdomain=None,
            limit=MAX_RESULTS,
            offset=0,
            settings=settings,
        )
    else:
        return f"Инструмента {name} нет. Доступны: {EXACT_SEARCH}, {SEMANTIC_SEARCH}.", []

    if not page.items:
        return "Ничего не нашлось.", []
    return "", list(page.items)


def product_ids(products: list[Product]) -> list[uuid.UUID]:
    return [product.id for product in products]
