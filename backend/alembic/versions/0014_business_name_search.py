"""trigram index on the shop name

Revision ID: 0014
Revises: 0013
Create Date: 2026-09-23
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # the catalogue search now also looks at the shop name; the extension itself came with 0009
    op.execute(
        "CREATE INDEX ix_businesses_display_name_trgm "
        "ON businesses USING gin (display_name gin_trgm_ops)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX ix_businesses_display_name_trgm")
