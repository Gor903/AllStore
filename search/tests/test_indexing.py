import uuid

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.embedder import FakeEmbedder
from app.indexing import candidates, reindex_all, reindex_one, search_text, source_hash
from app.tables import product_embeddings

pytestmark = pytest.mark.integration


def test_search_text_carries_what_a_buyer_would_say() -> None:
    text_value = search_text("Ваза «Гюмри»", "Керамика ручной работы", "Посуда", "Гончарная лавка")

    assert "Ваза «Гюмри»" in text_value
    assert "Посуда" in text_value
    assert "Гончарная лавка" in text_value
    assert "Керамика ручной работы" in text_value


def test_a_product_without_a_description_still_has_a_text() -> None:
    assert search_text("Ваза", None, "Посуда", "Лавка") == "Ваза. Посуда. Лавка"


def test_the_hash_follows_the_text() -> None:
    assert source_hash("Ваза") == source_hash("Ваза")
    assert source_hash("Ваза") != source_hash("Ваза, высота 30 см")


async def test_a_product_is_embedded_once(
    session: AsyncSession, embedder: FakeEmbedder, product: uuid.UUID
) -> None:
    written = await reindex_one(session, embedder, product)

    assert written is True
    stored = (
        await session.execute(
            select(product_embeddings.c.model).where(product_embeddings.c.product_id == product)
        )
    ).scalar_one()
    assert stored == embedder.name


async def test_an_unchanged_product_is_not_embedded_again(
    session: AsyncSession, embedder: FakeEmbedder, product: uuid.UUID
) -> None:
    """The sweep runs every few minutes; re-embedding a settled catalogue is its whole cost."""
    await reindex_one(session, embedder, product)

    assert await reindex_one(session, embedder, product) is False


async def test_an_edited_product_becomes_stale(
    session: AsyncSession, embedder: FakeEmbedder, product: uuid.UUID
) -> None:
    await reindex_one(session, embedder, product)
    await session.execute(
        text("update products set name = 'Ваза «Севан»' where id = :id"), {"id": product}
    )

    assert await reindex_one(session, embedder, product) is True


async def test_a_product_embedded_by_another_model_is_stale(
    session: AsyncSession, embedder: FakeEmbedder, product: uuid.UUID
) -> None:
    """Vectors of two models in one ranking compare numbers that mean different things."""
    await reindex_one(session, embedder, product)
    await session.execute(
        text("update product_embeddings set model = 'прежняя-модель' where product_id = :id"),
        {"id": product},
    )

    assert await reindex_one(session, embedder, product) is True


async def test_an_archived_product_is_not_indexed(
    session: AsyncSession, embedder: FakeEmbedder, product: uuid.UUID
) -> None:
    await session.execute(
        text("update products set archived_at = now() where id = :id"), {"id": product}
    )

    assert await candidates(session, limit=10, product_id=product) == []
    assert await reindex_one(session, embedder, product) is False


async def test_the_sweep_picks_up_what_the_ping_missed(
    session: AsyncSession, embedder: FakeEmbedder, product: uuid.UUID
) -> None:
    """Nobody told the service about this product — the sweep is what makes that survivable."""
    embedded = await reindex_all(session, embedder, batch_size=2)

    assert embedded >= 1
    stored = await session.scalar(
        text("select count(*) from product_embeddings where product_id = :id"), {"id": product}
    )
    assert stored == 1
