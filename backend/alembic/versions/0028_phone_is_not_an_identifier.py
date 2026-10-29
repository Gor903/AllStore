"""a phone nobody verified is not a thing anyone may own

Revision ID: 0028
Revises: 0027
Create Date: 2026-10-29

"""

from collections.abc import Sequence

from alembic import op

revision: str = "0028"
down_revision: str | None = "0027"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Drops the unique constraint on `users.phone`.

    Nobody ever checked that a number belonged to the person who typed it, and a unique
    constraint on an unchecked value is a way to take something from somebody: type a
    stranger's number into the registration form and they can no longer use their own.

    The column stays, and so does the index — it is still how a seller is looked up, and the
    administrator's search reads it. What goes is the claim that one number means one account.
    Verification would earn that claim back; until then it is not ours to make.
    """
    op.drop_constraint("users_phone_key", "users", type_="unique")
    # the lookups that used the unique index keep an index of their own
    op.create_index("ix_users_phone", "users", ["phone"])


def downgrade() -> None:
    """Will fail if two accounts have taken the same number in the meantime, and that is the
    honest outcome: there is no answer to which of them should keep it."""
    op.drop_index("ix_users_phone", table_name="users")
    op.create_unique_constraint("users_phone_key", "users", ["phone"])
