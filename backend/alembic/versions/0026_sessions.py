"""a session belongs to a device, and the server can take it back

Revision ID: 0026
Revises: 0025
Create Date: 2026-10-29

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0026"
down_revision: str | None = "0025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # a snapshot of the constraints in app.models.session: a migration must not follow the model
    op.create_table(
        "sessions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # constant across rotation: this is what makes "this device" nameable
        sa.Column("family_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False, unique=True),
        sa.Column(
            "replaced_by_id",
            sa.Uuid(),
            sa.ForeignKey("sessions.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("device_public_key", sa.Text(), nullable=True),
        sa.Column("user_agent", sa.String(length=255), nullable=True),
        # 45 characters is an IPv6 address with an embedded IPv4 one, the longest form there is
        sa.Column("ip", sa.String(length=45), nullable=True),
        sa.Column(
            "auth_method",
            sa.Enum("password", name="auth_method"),
            nullable=False,
            server_default="password",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("idle_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("absolute_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        # the newest device proof this session has accepted; a proof that is not newer than
        # this one has been seen before — see services/device_keys.py
        sa.Column("last_proof_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_reason", sa.String(length=255), nullable=True),
    )
    op.create_index("ix_sessions_user_id", "sessions", ["user_id"])
    # the device list, newest first
    op.create_index("ix_sessions_user_id_last_seen", "sessions", ["user_id", "last_seen_at"])
    # revoking one device means revoking its whole family
    op.create_index("ix_sessions_family_id", "sessions", ["family_id"])

    # Nothing is carried over. A refresh token is not a session — it has no device, no second
    # clock and no notion of a family, and inventing those values for rows that never had them
    # would put guesses in the one table the platform trusts about who is signed in. The cost
    # is that everybody signs in again once, which is also what a change of this size deserves.
    op.drop_table("refresh_tokens")


def downgrade() -> None:
    """Recreates the old table empty.

    The tokens that were in it are gone and could not be restored in any case: only their
    hashes were ever stored, and a hash opens nothing. Everybody signs in again, in the other
    direction this time.
    """
    op.create_table(
        "refresh_tokens",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("token_hash", sa.String(length=64), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "replaced_by_id",
            sa.Uuid(),
            sa.ForeignKey("refresh_tokens.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("user_agent", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_refresh_tokens_user_id", "refresh_tokens", ["user_id"])

    op.drop_index("ix_sessions_family_id", table_name="sessions")
    op.drop_index("ix_sessions_user_id_last_seen", table_name="sessions")
    op.drop_index("ix_sessions_user_id", table_name="sessions")
    op.drop_table("sessions")
    sa.Enum(name="auth_method").drop(op.get_bind(), checkfirst=True)
