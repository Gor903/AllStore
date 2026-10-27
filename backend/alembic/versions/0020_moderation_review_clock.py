"""moderation verdicts are ordered by the wall clock, not by the transaction

Revision ID: 0020
Revises: 0019
Create Date: 2026-10-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0020"
down_revision: str | None = "0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = ("moderation_reviews", "business_moderation_reviews")


def upgrade() -> None:
    # now() is the time the transaction began, so two verdicts written in one transaction
    # share a timestamp and the order between them is decided at random. The journal was
    # given clock_timestamp() for this reason in 0011; the verdict tables are read the same
    # way — newest first — and need the same thing.
    for table in TABLES:
        op.alter_column(
            table,
            "created_at",
            server_default=sa.text("clock_timestamp()"),
            existing_nullable=False,
            existing_type=sa.DateTime(timezone=True),
        )


def downgrade() -> None:
    for table in TABLES:
        op.alter_column(
            table,
            "created_at",
            server_default=sa.text("now()"),
            existing_nullable=False,
            existing_type=sa.DateTime(timezone=True),
        )
