"""product embeddings

Revision ID: 0013
Revises: 0012
Create Date: 2026-09-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# snapshot of app.models.embedding: a migration must not follow the model
EMBEDDING_DIMENSIONS = 1024


def upgrade() -> None:
    # pgvector is not a trusted extension: the role running migrations must be a superuser, or
    # an administrator must have created the extension beforehand. Both hold on the compose
    # stack and in CI; on a managed Postgres it is a one-time action for whoever owns the server
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "product_embeddings",
        # one product, one current embedding — hence the product is the key
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column("source_hash", sa.String(length=64), nullable=False),
        sa.Column("embedding", Vector(EMBEDDING_DIMENSIONS), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        # the embedding is an index of the product, not a fact about it: it goes with the product
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("product_id"),
    )
    # cosine distance, because that is what the search asks for. On a catalogue of this size a
    # full scan is instant and the index earns nothing — it is built now so that the day the
    # catalogue grows is not the day someone discovers the index was never there
    op.execute(
        "CREATE INDEX ix_product_embeddings_hnsw "
        "ON product_embeddings USING hnsw (embedding vector_cosine_ops)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX ix_product_embeddings_hnsw")
    op.drop_table("product_embeddings")
    # the extension stays: dropping it would take with it any other table that came to use
    # vectors, and an unused extension costs nothing
