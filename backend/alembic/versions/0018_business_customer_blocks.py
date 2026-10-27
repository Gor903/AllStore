"""business_customer_blocks

Revision ID: 0018
Revises: 0017
Create Date: 2026-10-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0018"
down_revision: str | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# a snapshot of the constraint in app.models.customer_block: a migration must not follow the model
REASON_GIVEN = r"reason ~ '\S'"


def upgrade() -> None:
    op.create_table(
        "business_customer_blocks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("business_id", sa.Uuid(), nullable=False),
        sa.Column("buyer_user_id", sa.Uuid(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_by_user_id", sa.Uuid(), nullable=True),
        sa.CheckConstraint(REASON_GIVEN, name="ck_business_customer_blocks_reason"),
        # RESTRICT: a record that disappears with what it is about is not a record
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["buyer_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["revoked_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_business_customer_blocks_business_id"),
        "business_customer_blocks",
        ["business_id"],
    )
    op.create_index(
        op.f("ix_business_customer_blocks_buyer_user_id"),
        "business_customer_blocks",
        ["buyer_user_id"],
    )
    # one block in force per shop-and-buyer pair, so lifting it is one action
    op.create_index(
        "uq_business_customer_blocks_in_force",
        "business_customer_blocks",
        ["business_id", "buyer_user_id"],
        unique=True,
        postgresql_where=sa.text("revoked_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_business_customer_blocks_in_force", table_name="business_customer_blocks")
    op.drop_index(
        op.f("ix_business_customer_blocks_buyer_user_id"), table_name="business_customer_blocks"
    )
    op.drop_index(
        op.f("ix_business_customer_blocks_business_id"), table_name="business_customer_blocks"
    )
    op.drop_table("business_customer_blocks")
