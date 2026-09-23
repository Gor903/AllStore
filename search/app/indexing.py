"""What a product looks like to the search, and how it gets there.

Indexing is a sweep, not a queue: a product is stale when its search text or the model that
embedded it no longer matches what the row says. That state lives in the same table as the
embedding, so a restart loses nothing and no broker is needed (docs/rag-first.md, раздел 25).
"""

import hashlib
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.embedder import Embedder
from app.tables import businesses, categories, product_embeddings, products


@dataclass(frozen=True)
class Candidate:
    product_id: uuid.UUID
    text: str
    source_hash: str
    stored_hash: str | None
    stored_model: str | None

    def is_stale(self, model: str) -> bool:
        return self.stored_hash != self.source_hash or self.stored_model != model


def search_text(name: str, description: str | None, category: str, shop: str) -> str:
    """The text a product is found by.

    Name, category, shop and description in one line (docs/rag-first.md, раздел 14). The shop
    is in there because "керамика из Гюмри" is a thing buyers look for; the category, because a
    name alone rarely says what kind of thing it is.
    """
    parts = [name.strip(), category.strip(), shop.strip()]
    if description is not None and description.strip():
        parts.append(description.strip())
    return ". ".join(part for part in parts if part)


def source_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


async def candidates(
    session: AsyncSession,
    limit: int,
    after: uuid.UUID | None = None,
    product_id: uuid.UUID | None = None,
) -> list[Candidate]:
    """One page of products with whatever embedding they currently have.

    Archived products are skipped: the seller took them off the shelf for good, and embedding
    them would cost the same as embedding the live catalogue twice over on a busy shop.
    """
    statement = (
        select(
            products.c.id,
            products.c.name,
            products.c.description,
            categories.c.name.label("category"),
            businesses.c.display_name.label("shop"),
            product_embeddings.c.source_hash,
            product_embeddings.c.model,
        )
        .select_from(
            products.join(categories, categories.c.id == products.c.category_id)
            .join(businesses, businesses.c.id == products.c.business_id)
            .outerjoin(product_embeddings, product_embeddings.c.product_id == products.c.id)
        )
        .where(products.c.archived_at.is_(None))
        .order_by(products.c.id)
        .limit(limit)
    )
    if after is not None:
        statement = statement.where(products.c.id > after)
    if product_id is not None:
        statement = statement.where(products.c.id == product_id)

    rows = (await session.execute(statement)).all()
    found = []
    for row in rows:
        text = search_text(row.name, row.description, row.category, row.shop)
        found.append(
            Candidate(
                product_id=row.id,
                text=text,
                source_hash=source_hash(text),
                stored_hash=row.source_hash,
                stored_model=row.model,
            )
        )
    return found


async def store(session: AsyncSession, embedder: Embedder, batch: list[Candidate]) -> None:
    """Embeds a batch and writes it, replacing whatever was there for those products."""
    if not batch:
        return
    vectors = embedder.embed_documents([item.text for item in batch])
    rows = [
        {
            "product_id": item.product_id,
            "model": embedder.name,
            "source_hash": item.source_hash,
            "embedding": vector,
        }
        for item, vector in zip(batch, vectors, strict=True)
    ]
    statement = insert(product_embeddings).values(rows)
    await session.execute(
        statement.on_conflict_do_update(
            index_elements=[product_embeddings.c.product_id],
            set_={
                "model": statement.excluded.model,
                "source_hash": statement.excluded.source_hash,
                "embedding": statement.excluded.embedding,
                "updated_at": statement.excluded.updated_at,
            },
        )
    )
    await session.commit()


async def reindex_all(session: AsyncSession, embedder: Embedder, batch_size: int) -> int:
    """Brings every stale product up to date. Returns how many were re-embedded.

    Walks the catalogue by primary key instead of holding one long transaction: the sweep runs
    beside live traffic, and a page going stale again right after it was read is not a problem —
    the next sweep picks it up.
    """
    embedded = 0
    after: uuid.UUID | None = None
    while True:
        page = await candidates(session, batch_size, after=after)
        if not page:
            return embedded
        after = page[-1].product_id
        stale = [item for item in page if item.is_stale(embedder.name)]
        await store(session, embedder, stale)
        embedded += len(stale)


async def reindex_one(session: AsyncSession, embedder: Embedder, product_id: uuid.UUID) -> bool:
    """The path behind the ping from backend: one product, straight to it.

    Returns whether anything was written — a product that is already current, archived or gone
    is not an error here. The sweep is what guarantees the catalogue converges; this only makes
    the common case immediate.
    """
    page = await candidates(session, limit=1, product_id=product_id)
    stale = [item for item in page if item.is_stale(embedder.name)]
    await store(session, embedder, stale)
    return bool(stale)
