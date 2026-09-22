"""social_links

Revision ID: 0010
Revises: 0009
Create Date: 2026-09-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# snapshot of the constraint in app.models.contact: a migration must not follow the model
VALUE_NOT_BLANK = r"value ~ '\S'"


def upgrade() -> None:
    op.create_table(
        "social_links",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("business_id", sa.Uuid(), nullable=False),
        sa.Column(
            "platform",
            sa.Enum(
                "phone",
                "whatsapp",
                "telegram",
                "viber",
                "instagram",
                "facebook",
                name="contact_platform",
            ),
            nullable=False,
        ),
        sa.Column("value", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(VALUE_NOT_BLANK, name="ck_social_links_value_not_blank"),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("business_id", "platform", name="uq_social_links_business_platform"),
    )
    op.create_index(
        op.f("ix_social_links_business_id"), "social_links", ["business_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_social_links_business_id"), table_name="social_links")
    op.drop_table("social_links")
    # drop_table leaves the enum type behind — without this a repeated upgrade hits an existing type
    sa.Enum(name="contact_platform").drop(op.get_bind(), checkfirst=False)
