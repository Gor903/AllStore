"""moderation_reviews

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# snapshot of the constraint in app.models.moderation: a migration must not follow the model
REASON_REQUIRED = r"decision <> 'rejected' OR (reason IS NOT NULL AND reason ~ '\S')"


def upgrade() -> None:
    op.create_table(
        "moderation_reviews",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("moderator_id", sa.Uuid(), nullable=True),
        sa.Column(
            "decision",
            sa.Enum("approved", "rejected", "hidden", name="moderation_decision"),
            nullable=False,
        ),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(REASON_REQUIRED, name="ck_moderation_reviews_reason_for_rejection"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["moderator_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_moderation_reviews_product_id"), "moderation_reviews", ["product_id"], unique=False
    )
    op.create_index(
        op.f("ix_moderation_reviews_moderator_id"),
        "moderation_reviews",
        ["moderator_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_moderation_reviews_moderator_id"), table_name="moderation_reviews")
    op.drop_index(op.f("ix_moderation_reviews_product_id"), table_name="moderation_reviews")
    op.drop_table("moderation_reviews")
    # drop_table leaves the enum type behind — without this a repeated upgrade hits an existing type
    sa.Enum(name="moderation_decision").drop(op.get_bind(), checkfirst=False)
