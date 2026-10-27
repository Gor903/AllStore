"""account_blocks

Revision ID: 0016
Revises: 0015
Create Date: 2026-10-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# a snapshot of the constraint in app.models.account_block: a migration must not follow the model
REASON_GIVEN = r"reason ~ '\S'"


def upgrade() -> None:
    op.create_table(
        "account_blocks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("revoke_reason", sa.Text(), nullable=True),
        sa.CheckConstraint(REASON_GIVEN, name="ck_account_blocks_reason"),
        # RESTRICT, not CASCADE: a ban that vanishes with the account it was about is not a record
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        # losing the actor must not erase what they decided
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["revoked_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_account_blocks_user_id"), "account_blocks", ["user_id"])
    op.create_index(op.f("ix_account_blocks_actor_user_id"), "account_blocks", ["actor_user_id"])
    # one ban in force per account, so two moderators deciding at once produce one ban
    op.create_index(
        "uq_account_blocks_in_force",
        "account_blocks",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("revoked_at IS NULL"),
    )

    # accounts already barred before this table existed: without a row they would have a status
    # nobody can explain and no way to lift it through the history. The reason says as much.
    op.execute(
        sa.text(
            "INSERT INTO account_blocks (id, user_id, actor_user_id, reason) "
            "SELECT gen_random_uuid(), id, NULL, "
            "'Блокировка до введения журнала блокировок; причина указана в общем журнале' "
            "FROM users WHERE status = 'blocked'"
        )
    )


def downgrade() -> None:
    op.drop_index("uq_account_blocks_in_force", table_name="account_blocks")
    op.drop_index(op.f("ix_account_blocks_actor_user_id"), table_name="account_blocks")
    op.drop_index(op.f("ix_account_blocks_user_id"), table_name="account_blocks")
    op.drop_table("account_blocks")
