"""a password somebody else typed stops working after three days

Revision ID: 0031
Revises: 0030
Create Date: 2026-10-30

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0031"
down_revision: str | None = "0030"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # a snapshot of the column in app.models.user: a migration must not follow the model
    op.add_column(
        "users",
        sa.Column("password_handed_over_at", sa.DateTime(timezone=True), nullable=True),
    )
    # Accounts already owing a change are stamped with now rather than with when it actually
    # happened, which nobody wrote down. Backdating would expire them this minute and lock
    # out whoever has not got round to it; this gives every one of them the full window from
    # the moment the rule starts existing, which is the only honest reading of "from now on".
    op.execute(
        "UPDATE users SET password_handed_over_at = now() WHERE must_change_password IS TRUE"
    )


def downgrade() -> None:
    op.drop_column("users", "password_handed_over_at")
