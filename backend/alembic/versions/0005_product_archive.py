"""products.archived_at

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("products", sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True))
    # the dashboard lists live products of one business, so the index covers exactly that query
    op.create_index(
        "ix_products_business_id_live",
        "products",
        ["business_id"],
        unique=False,
        postgresql_where=sa.text("archived_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_products_business_id_live", table_name="products")
    op.drop_column("products", "archived_at")
