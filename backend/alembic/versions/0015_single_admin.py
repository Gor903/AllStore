"""single administrator

Revision ID: 0015
Revises: 0014
Create Date: 2026-10-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SINGLE_ADMIN_INDEX = "uq_users_single_admin"


def upgrade() -> None:
    # Fail before the index does, with something an operator can act on. A unique violation
    # here would say "key (role)=(admin) is duplicated" and leave them guessing which accounts.
    existing = op.get_bind().execute(
        sa.text("SELECT string_agg(email, ', ' ORDER BY email) FROM users WHERE role = 'admin'"),
    )
    emails = existing.scalar_one_or_none()
    if emails is not None and "," in emails:
        raise RuntimeError(
            "The platform has more than one administrator and from this revision on it may "
            f"have exactly one. Demote all but one by hand first: {emails}"
        )

    # the invariant the whole role hierarchy rests on, enforced where races cannot talk their
    # way past it: two bootstraps, or a bootstrap racing a role change, meet this index
    op.create_index(
        SINGLE_ADMIN_INDEX,
        "users",
        ["role"],
        unique=True,
        postgresql_where=sa.text("role = 'admin'"),
    )


def downgrade() -> None:
    op.drop_index(SINGLE_ADMIN_INDEX, table_name="users")
