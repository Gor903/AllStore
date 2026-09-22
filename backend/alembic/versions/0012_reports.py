"""reports

Revision ID: 0012
Revises: 0011
Create Date: 2026-09-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# snapshots of the constraints in app.models.report: a migration must not follow the model
ONE_SUBJECT = "(product_id IS NULL) <> (business_id IS NULL)"
RESOLUTION_REASONED = (
    r"status <> 'dismissed' OR (resolution_reason IS NOT NULL AND resolution_reason ~ '\S')"
)


def upgrade() -> None:
    op.create_table(
        "reports",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("reporter_user_id", sa.Uuid(), nullable=True),
        sa.Column("product_id", sa.Uuid(), nullable=True),
        sa.Column("business_id", sa.Uuid(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column(
            "status",
            sa.Enum("open", "upheld", "dismissed", name="report_status"),
            nullable=False,
        ),
        sa.Column("resolved_by", sa.Uuid(), nullable=True),
        sa.Column("resolution_reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(ONE_SUBJECT, name="ck_reports_one_subject"),
        sa.CheckConstraint(RESOLUTION_REASONED, name="ck_reports_reason_for_dismissal"),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE"),
        # losing an account must not erase the complaint or who closed it
        sa.ForeignKeyConstraint(["reporter_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["resolved_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_reports_product_id"), "reports", ["product_id"])
    op.create_index(op.f("ix_reports_business_id"), "reports", ["business_id"])
    op.create_index(op.f("ix_reports_status"), "reports", ["status"])


def downgrade() -> None:
    op.drop_index(op.f("ix_reports_status"), table_name="reports")
    op.drop_index(op.f("ix_reports_business_id"), table_name="reports")
    op.drop_index(op.f("ix_reports_product_id"), table_name="reports")
    op.drop_table("reports")
    # drop_table leaves the enum type behind — without this a repeated upgrade hits it
    sa.Enum(name="report_status").drop(op.get_bind(), checkfirst=False)
