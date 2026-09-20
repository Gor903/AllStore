"""trigram indexes for the catalogue search

Revision ID: 0009
Revises: 0008
Create Date: 2026-09-21
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # pg_trgm is a trusted extension since PostgreSQL 13, so the database owner may create it
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    # trigrams, not full text: the catalogue carries Russian, Armenian and English side by
    # side, and one text search configuration cannot stem all three. A substring match also
    # finds a part of a word, which is what a shopper types
    op.execute("CREATE INDEX ix_products_name_trgm ON products USING gin (name gin_trgm_ops)")
    op.execute(
        "CREATE INDEX ix_products_description_trgm ON products USING gin (description gin_trgm_ops)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX ix_products_description_trgm")
    op.execute("DROP INDEX ix_products_name_trgm")
    # the extension stays: another table may have come to rely on it
