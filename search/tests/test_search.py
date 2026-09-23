import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.embedder import FakeEmbedder
from app.indexing import reindex_one, search_text
from app.search import find

pytestmark = pytest.mark.integration


async def test_the_search_returns_identifiers_and_a_score(
    session: AsyncSession, embedder: FakeEmbedder, product: uuid.UUID
) -> None:
    await reindex_one(session, embedder, product)

    # the same text the product was indexed by: with a deterministic stand-in that is an
    # exact hit, which is what makes the score assertion below mean anything
    indexed_as = search_text("Ваза «Гюмри»", "Керамика ручной работы", "Посуда", "Гончарная лавка")

    matches = await find(session, embedder, indexed_as, limit=5)

    found = {match.product_id: match.score for match in matches}
    assert product in found
    # the fake embedder is deterministic: the exact search text scores as a perfect match
    assert found[product] == pytest.approx(1.0, abs=1e-6)


async def test_vectors_of_another_model_are_not_ranked(
    session: AsyncSession, embedder: FakeEmbedder, product: uuid.UUID
) -> None:
    await reindex_one(session, embedder, product)
    await session.execute(
        text("update product_embeddings set model = 'прежняя-модель' where product_id = :id"),
        {"id": product},
    )

    matches = await find(session, embedder, "Ваза", limit=5)

    assert all(match.product_id != product for match in matches)


async def test_an_unindexed_catalogue_answers_empty(
    session: AsyncSession, embedder: FakeEmbedder
) -> None:
    """Before the first sweep the service has nothing to say — and says exactly that."""
    await session.execute(text("delete from product_embeddings"))

    assert await find(session, embedder, "ваза", limit=5) == []
