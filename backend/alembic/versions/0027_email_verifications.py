"""an address is somebody's only once they answer a letter at it

Revision ID: 0027
Revises: 0026
Create Date: 2026-10-29

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0027"
down_revision: str | None = "0026"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # a snapshot of the constraints in app.models.email_verification: a migration must not
    # follow the model
    op.create_table(
        "email_verifications",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("token_hash", sa.String(length=64), nullable=False, unique=True),
        # equal to the account's own address when confirming it, different when moving
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_email_verifications_user_id", "email_verifications", ["user_id"])

    # Nobody is marked as verified by this migration. Every address on the platform arrived
    # through a form that never checked it, so saying they are confirmed would be writing down
    # something nobody established — and `email_verified_at` meaning nothing is the condition
    # this whole change exists to end. Existing accounts are asked, like everybody else.


def downgrade() -> None:
    op.drop_index("ix_email_verifications_user_id", table_name="email_verifications")
    op.drop_table("email_verifications")
