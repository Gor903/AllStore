"""product_revisions

Revision ID: 0021
Revises: 0020
Create Date: 2026-10-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0021"
down_revision: str | None = "0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# a snapshot of the constraint in app.models.product_revision
REASON_FOR_REJECTION = r"status <> 'rejected' OR (reason IS NOT NULL AND reason ~ '\S')"


def upgrade() -> None:
    op.create_table(
        "product_revisions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("category_id", sa.Uuid(), nullable=False),
        sa.Column(
            "status",
            sa.Enum("pending", "approved", "rejected", "superseded", name="revision_status"),
            nullable=False,
        ),
        sa.Column("moderator_id", sa.Uuid(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(REASON_FOR_REJECTION, name="ck_product_revisions_reason_for_rejection"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE"),
        # RESTRICT, as on the product: removing a category must not take proposals with it
        sa.ForeignKeyConstraint(["category_id"], ["categories.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["moderator_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_product_revisions_product_id"), "product_revisions", ["product_id"])
    op.create_index(op.f("ix_product_revisions_status"), "product_revisions", ["status"])
    # one proposal in the queue per product, so a moderator never has to pick between two
    op.create_index(
        "uq_product_revisions_pending",
        "product_revisions",
        ["product_id"],
        unique=True,
        postgresql_where=sa.text("status = 'pending'"),
    )

    # which revision a verdict was about. Nullable: every verdict passed before this table
    # existed was about the product as a whole, and inventing a revision for it would be
    # inventing history.
    op.add_column("moderation_reviews", sa.Column("revision_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_moderation_reviews_revision_id",
        "moderation_reviews",
        "product_revisions",
        ["revision_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # Every product that already exists gets the revision it would have had. A product the
    # queue is holding gets a pending one — otherwise it would vanish from the queue, which
    # now lists proposals rather than products; everything else gets a closed one carrying
    # the text the buyer is looking at.
    op.execute(
        sa.text(
            "INSERT INTO product_revisions "
            "(id, product_id, name, description, category_id, status, created_at, decided_at) "
            "SELECT gen_random_uuid(), id, name, description, category_id, "
            "  CASE WHEN moderation_status = 'pending' THEN 'pending'::revision_status "
            "       WHEN moderation_status = 'approved' THEN 'approved'::revision_status "
            "       ELSE 'rejected'::revision_status END, "
            "  created_at, "
            "  CASE WHEN moderation_status = 'pending' THEN NULL ELSE updated_at END "
            "FROM products"
        )
    )
    # a refused product needs a reason on its revision, and the one it has is in its verdict
    op.execute(
        sa.text(
            "UPDATE product_revisions SET reason = COALESCE(("
            "  SELECT r.reason FROM moderation_reviews r "
            "  WHERE r.product_id = product_revisions.product_id AND r.decision = 'rejected' "
            "  ORDER BY r.created_at DESC LIMIT 1"
            "), 'Причина не сохранилась: решение принято до появления ревизий') "
            "WHERE status = 'rejected'"
        )
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_moderation_reviews_revision_id", "moderation_reviews", type_="foreignkey"
    )
    op.drop_column("moderation_reviews", "revision_id")
    op.drop_index("uq_product_revisions_pending", table_name="product_revisions")
    op.drop_index(op.f("ix_product_revisions_status"), table_name="product_revisions")
    op.drop_index(op.f("ix_product_revisions_product_id"), table_name="product_revisions")
    op.drop_table("product_revisions")
    sa.Enum(name="revision_status").drop(op.get_bind(), checkfirst=True)
