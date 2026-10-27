"""moderator_invitations

Revision ID: 0017
Revises: 0016
Create Date: 2026-10-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0017"
down_revision: str | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "moderator_invitations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        # the sha256 only: a database leak must not yield a usable invitation
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("accepted_user_id", sa.Uuid(), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_by_user_id", sa.Uuid(), nullable=True),
        # losing an account must not erase who invited whom
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["accepted_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["revoked_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index(op.f("ix_moderator_invitations_email"), "moderator_invitations", ["email"])
    op.create_index(
        op.f("ix_moderator_invitations_created_by_user_id"),
        "moderator_invitations",
        ["created_by_user_id"],
    )
    # one live invitation per address, so "which link works" never has two answers
    op.create_index(
        "uq_moderator_invitations_live",
        "moderator_invitations",
        ["email"],
        unique=True,
        postgresql_where=sa.text("used_at IS NULL AND revoked_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_moderator_invitations_live", table_name="moderator_invitations")
    op.drop_index(
        op.f("ix_moderator_invitations_created_by_user_id"), table_name="moderator_invitations"
    )
    op.drop_index(op.f("ix_moderator_invitations_email"), table_name="moderator_invitations")
    op.drop_table("moderator_invitations")
