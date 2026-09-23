import asyncio
import logging
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from typing import Annotated

from fastapi import Depends, FastAPI, Query
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app import db, indexing, search
from app.config import Settings, get_settings
from app.embedder import Embedder, build_embedder

logger = logging.getLogger("search")

QUERY_MAX_LENGTH = 500

# one sweep at a time: the periodic pass and a hand-triggered one would otherwise embed the
# same products twice over — harmless for the data, wasteful with the only slow resource here
_sweeping = asyncio.Lock()


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=QUERY_MAX_LENGTH)
    limit: int = Field(default=20, ge=1, le=100)


class MatchRead(BaseModel):
    product_id: uuid.UUID
    score: float


class SearchResponse(BaseModel):
    """Identifiers and nothing else — the caller owns what a visitor may see."""

    model: str
    matches: list[MatchRead]


class ReindexResponse(BaseModel):
    embedded: int


class HealthResponse(BaseModel):
    status: str
    model: str
    indexed: int


def create_app() -> FastAPI:
    settings = get_settings()
    logging.basicConfig(level=settings.log_level)
    db.configure(settings)
    embedder = build_embedder(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        sweeper = asyncio.create_task(sweep_forever(settings, embedder))
        try:
            yield
        finally:
            sweeper.cancel()
            with suppress(asyncio.CancelledError):
                await sweeper
            await db.dispose()

    app = FastAPI(title="AllStore Search", version="0.1.0", lifespan=lifespan)

    SessionDep = Annotated[AsyncSession, Depends(db.get_session)]

    @app.get("/health", response_model=HealthResponse)
    async def health(session: SessionDep) -> HealthResponse:
        indexed = await session.scalar(
            text("select count(*) from product_embeddings where model = :model"),
            {"model": embedder.name},
        )
        return HealthResponse(status="ok", model=embedder.name, indexed=int(indexed or 0))

    @app.post("/search", response_model=SearchResponse)
    async def run_search(payload: SearchRequest, session: SessionDep) -> SearchResponse:
        matches = await search.find(session, embedder, payload.query, payload.limit)
        return SearchResponse(
            model=embedder.name,
            matches=[MatchRead(product_id=m.product_id, score=m.score) for m in matches],
        )

    @app.post("/reindex", response_model=ReindexResponse)
    async def run_reindex(
        session: SessionDep, product_id: Annotated[uuid.UUID | None, Query()] = None
    ) -> ReindexResponse:
        """Один товар — путь пинга от backend; без него — обход всего каталога."""
        if product_id is not None:
            written = await indexing.reindex_one(session, embedder, product_id)
            return ReindexResponse(embedded=int(written))
        async with _sweeping:
            embedded = await indexing.reindex_all(session, embedder, settings.batch_size)
        return ReindexResponse(embedded=embedded)

    return app


async def sweep_forever(settings: Settings, embedder: Embedder) -> None:
    """The safety net under the ping from backend.

    A lost ping, a restart in the middle of a batch, a product edited straight in the database
    by a seeding script — all of it converges here, because staleness is a fact stored in the
    row rather than a message someone has to receive.
    """
    while True:
        try:
            async with _sweeping, db.session_factory()() as session:
                embedded = await indexing.reindex_all(session, embedder, settings.batch_size)
            if embedded:
                logger.info("переиндексировано товаров: %s", embedded)
        except asyncio.CancelledError:
            raise
        except Exception:
            # a sweep that fails is not a service that failed: search keeps answering with
            # whatever is already indexed, and the next pass tries again
            logger.exception("обход каталога не удался")
        await asyncio.sleep(settings.reindex_interval_seconds)


app = create_app()
