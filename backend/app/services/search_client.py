"""The one place backend talks to the search service.

Everything here is best-effort by design. The search is an addition to the catalogue, not a
part of it: when the service is slow, broken or simply not deployed, the catalogue answers
exactly as it did before semantic search existed (ADR 10 — the site works without the AI
service). That is why nothing in this module raises.
"""

import uuid

import httpx

from app.core.config import Settings
from app.core.logging import get_logger

logger = get_logger(__name__)


async def semantic_ids(settings: Settings, query: str, limit: int) -> list[uuid.UUID]:
    """Products the search considers close in meaning, best first.

    An empty list means "nothing to add" — it is the answer both when the service found
    nothing and when it could not be reached, because the caller does the same thing in both
    cases: shows the exact matches it already has.
    """
    if settings.search_service_url is None:
        return []
    url = f"{settings.search_service_url.rstrip('/')}/search"
    try:
        async with httpx.AsyncClient(timeout=settings.search_timeout_seconds) as client:
            response = await client.post(url, json={"query": query, "limit": limit})
            response.raise_for_status()
            matches = response.json()["matches"]
    except (httpx.HTTPError, KeyError, ValueError):
        logger.warning("поиск по смыслу недоступен, выдача осталась точной", exc_info=True)
        return []
    return [uuid.UUID(match["product_id"]) for match in matches]


async def product_changed(settings: Settings, product_id: uuid.UUID) -> None:
    """Tells the search that a product is worth re-reading.

    A hint, not a command: the service sweeps the catalogue on its own and would notice the
    change within minutes anyway. This only makes the common case immediate, so a failed ping
    is logged and forgotten rather than retried.
    """
    if settings.search_service_url is None:
        return
    url = f"{settings.search_service_url.rstrip('/')}/reindex"
    try:
        async with httpx.AsyncClient(timeout=settings.search_timeout_seconds) as client:
            response = await client.post(url, params={"product_id": str(product_id)})
            response.raise_for_status()
    except httpx.HTTPError:
        logger.info("не удалось сообщить поиску о правке товара %s", product_id, exc_info=True)
