"""Vector search: a query in, product identifiers out.

Deliberately nothing else. The service does not know which products a visitor may see — that
is decided once, by backend, when it turns these identifiers back into products
(docs/rag-first.md, раздел 12: PostgreSQL stays the source of truth). A second place deciding
visibility is a second place to get it wrong.
"""

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.embedder import Embedder
from app.tables import product_embeddings


@dataclass(frozen=True)
class Match:
    product_id: uuid.UUID
    # 1.0 means the query and the product point the same way, 0.0 means unrelated
    score: float


async def find(session: AsyncSession, embedder: Embedder, query: str, limit: int) -> list[Match]:
    vector = embedder.embed_query(query)
    distance = product_embeddings.c.embedding.cosine_distance(vector)
    statement = (
        select(product_embeddings.c.product_id, distance.label("distance"))
        # only what the current model produced: vectors of two models in one ranking compare
        # numbers that mean different things
        .where(product_embeddings.c.model == embedder.name)
        .order_by(distance)
        .limit(limit)
    )
    rows = (await session.execute(statement)).all()
    return [Match(product_id=row.product_id, score=1.0 - float(row.distance)) for row in rows]
