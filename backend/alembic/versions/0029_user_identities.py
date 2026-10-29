"""an account may have another way in, and the password stops being compulsory

Revision ID: 0029
Revises: 0028
Create Date: 2026-10-29

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0029"
down_revision: str | None = "0028"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # a snapshot of the constraints in app.models.identity: a migration must not follow the model
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
        # what the provider calls this person, and the only thing here that is an identity
        sa.Column("provider_subject", sa.String(length=255), nullable=False),
        sa.Column("email_at_link", sa.String(length=320), nullable=False),
        sa.Column("linked_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        # one provider account opens one platform account, and the index is what makes that
        # true under a race rather than merely intended
        sa.UniqueConstraint("provider", "provider_subject", name="uq_identity_provider_subject"),
    )
    op.create_index("ix_user_identities_user_id", "user_identities", ["user_id"])

    # An account that only ever signs in with Google has no password, and a column that
    # insists on one would have to be filled with something — and whatever that something
    # was, it would be a value somebody could try to guess against.
    op.alter_column("users", "password_hash", existing_type=sa.String(length=255), nullable=True)


def downgrade() -> None:
    """Will fail if any account has no password, and that is the honest outcome: there is
    nothing to put there that would not be a lie about how that account signs in."""
    op.alter_column("users", "password_hash", existing_type=sa.String(length=255), nullable=False)
    op.drop_index("ix_user_identities_user_id", table_name="user_identities")
    op.drop_table("user_identities")
    sa.Enum(name="identity_provider").drop(op.get_bind(), checkfirst=True)
