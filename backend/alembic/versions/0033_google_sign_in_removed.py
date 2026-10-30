"""signing in with a provider is gone, and the password is compulsory again

Revision ID: 0033
Revises: 0032
Create Date: 2026-10-30

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0033"
down_revision: str | None = "0032"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Deliberately before the column change, so a database holding accounts that signed in
    # this way fails on the next statement with the table still intact.
    op.drop_index("ix_user_identities_user_id", table_name="user_identities")
    op.drop_table("user_identities")
    sa.Enum(name="identity_provider").drop(op.get_bind(), checkfirst=True)

    # Will fail if any account has no password, and that is the honest outcome: such an
    # account signed in with Google, Google is gone, and anything put in this column would be
    # a value somebody could try to guess against. Give those accounts a password first.
    op.alter_column("users", "password_hash", existing_type=sa.String(length=255), nullable=False)


def downgrade() -> None:
    """Restores what migration 0029 created. The rows are not restored — the table is."""
    op.alter_column("users", "password_hash", existing_type=sa.String(length=255), nullable=True)
    op.create_table(
        "user_identities",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("provider", sa.Enum("google", name="identity_provider"), nullable=False),
        sa.Column("provider_subject", sa.String(length=255), nullable=False),
        sa.Column("email_at_link", sa.String(length=320), nullable=False),
        sa.Column("linked_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("provider", "provider_subject", name="uq_identity_provider_subject"),
    )
    op.create_index("ix_user_identities_user_id", "user_identities", ["user_id"])
