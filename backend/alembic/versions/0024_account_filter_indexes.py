"""indexes for the administrator's filters

Revision ID: 0024
Revises: 0023
Create Date: 2026-10-28
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0024"
down_revision: str | None = "0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # the shape the list is read in: narrow by role and status, newest first. Without it the
    # filtered listing is a sequential scan plus a sort — survivable at a few hundred accounts,
    # not at the ten thousand this is sized for
    op.execute("CREATE INDEX ix_users_role_status_created ON users (role, status, created_at DESC)")
    # the search is a substring of an address or a phone, which no btree can answer. Same
    # choice and the same reasons as the catalogue: see 0009
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute("CREATE INDEX ix_users_email_trgm ON users USING gin (email gin_trgm_ops)")
    op.execute("CREATE INDEX ix_users_phone_trgm ON users USING gin (phone gin_trgm_ops)")


def downgrade() -> None:
    op.execute("DROP INDEX ix_users_phone_trgm")
    op.execute("DROP INDEX ix_users_email_trgm")
    op.execute("DROP INDEX ix_users_role_status_created")
    # the extension stays: the catalogue relies on it
