"""when the account last proved who it was

Revision ID: 0023
Revises: 0022
Create Date: 2026-10-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0023"
down_revision: str | None = "0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # null for everybody who already exists: "has not logged in since this shipped" is the
    # truth, and backfilling from refresh tokens would record token rotation as a login
    op.add_column("users", sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True))
    # the administrator sorts by this column; nulls last, so accounts that never came back
    # do not crowd out the ones that did
    op.create_index(
        "ix_users_last_login_at",
        "users",
        [sa.text("last_login_at DESC NULLS LAST")],
    )


def downgrade() -> None:
    op.drop_index("ix_users_last_login_at", table_name="users")
    op.drop_column("users", "last_login_at")
