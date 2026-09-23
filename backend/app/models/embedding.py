import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# multilingual-e5-base, see docs/rag-first.md, раздел 27: one number per dimension, fixed at
# rest — changing the model to one of another width is a migration, not a configuration change
EMBEDDING_DIMENSIONS = 768
MODEL_MAX_LENGTH = 128
# sha256 of the search text, hex
SOURCE_HASH_LENGTH = 64


class ProductEmbedding(Base):
    """The search index of one product — an addition to the product, never a copy of it.

    Written and read by the search service alone (docs/rag-first.md, раздел 16); the model
    lives here because the schema of this database is owned by backend migrations and by
    nothing else (AllStore_build_plan.md, раздел 6). Without it Alembic autogenerate would
    see a table nobody declared and propose dropping it.

    `model` and `source_hash` together are what makes a row stale: a product whose search
    text changed, or one embedded by a model we no longer use, is re-embedded in the
    background (раздел 25) rather than at the moment the seller saves.
    """

    __tablename__ = "product_embeddings"

    # the product is the key: one product, one current embedding
    product_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), primary_key=True
    )
    model: Mapped[str] = mapped_column(String(MODEL_MAX_LENGTH), nullable=False)
    source_hash: Mapped[str] = mapped_column(String(SOURCE_HASH_LENGTH), nullable=False)
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIMENSIONS), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
