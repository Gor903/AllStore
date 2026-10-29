"""a password is one thing somebody knows, and for staff it stops being enough

Revision ID: 0030
Revises: 0029
Create Date: 2026-10-29

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0030"
down_revision: str | None = "0029"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # a snapshot of the constraints in app.models.totp: a migration must not follow the model
    op.create_table(
        "totp_credentials",
        sa.Column("id", sa.Uuid(), primary_key=True),
        # unique: one authenticator per account, because two is two to keep track of
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        # encrypted, not hashed: codes have to be computed from it — see core/vault.py
        sa.Column("secret_encrypted", sa.Text(), nullable=False),
        # null until a code has been typed: an enrolment nobody finished must not lock anybody
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        # the last step spent, so one code read over a shoulder does not work twice
        sa.Column("last_used_step", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_totp_credentials_user_id", "totp_credentials", ["user_id"])

    op.create_table(
        "totp_recovery_codes",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("code_hash", sa.String(length=64), nullable=False, unique=True),
        # kept after use: deleting a spent code would make it indistinguishable from one that
        # never existed, and that distinction is what stops it being spent twice
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_totp_recovery_codes_user_id", "totp_recovery_codes", ["user_id"])

    # Nobody is enrolled by this migration, and nobody could be: a second factor is a secret
    # shared with a telephone, and there is no telephone to share one with from here. Existing
    # staff are asked on their next sign-in, which is what the gate in deps/auth.py is for.


def downgrade() -> None:
    op.drop_index("ix_totp_recovery_codes_user_id", table_name="totp_recovery_codes")
    op.drop_table("totp_recovery_codes")
    op.drop_index("ix_totp_credentials_user_id", table_name="totp_credentials")
    op.drop_table("totp_credentials")
