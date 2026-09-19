"""stores

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# snapshot of app.models.store.SUBDOMAIN_PATTERN: a migration must not follow the model
SUBDOMAIN_PATTERN = r"^[a-z0-9][a-z0-9-]{1,61}[a-z0-9]$"


def upgrade() -> None:
    op.create_table(
        "stores",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("business_id", sa.Uuid(), nullable=False),
        sa.Column("subdomain", sa.String(length=63), nullable=False),
        sa.Column("logo_url", sa.String(length=1024), nullable=True),
        sa.Column("banner_url", sa.String(length=1024), nullable=True),
        sa.Column("primary_color", sa.String(length=7), nullable=True),
        sa.Column("secondary_color", sa.String(length=7), nullable=True),
        sa.Column("theme_id", sa.String(length=32), nullable=False),
        sa.Column(
            "status",
            sa.Enum("draft", "active", "suspended", "blocked", name="store_status"),
            nullable=False,
        ),
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
        sa.CheckConstraint(f"subdomain ~ '{SUBDOMAIN_PATTERN}'", name="ck_stores_subdomain_format"),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_stores_business_id"), "stores", ["business_id"], unique=True)
    op.create_index(op.f("ix_stores_subdomain"), "stores", ["subdomain"], unique=True)


def downgrade() -> None:
    op.drop_index(op.f("ix_stores_subdomain"), table_name="stores")
    op.drop_index(op.f("ix_stores_business_id"), table_name="stores")
    op.drop_table("stores")
    # drop_table leaves the enum type behind — without this a repeated upgrade hits an existing type
    sa.Enum(name="store_status").drop(op.get_bind(), checkfirst=False)
