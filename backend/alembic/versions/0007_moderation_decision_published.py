"""moderation_decision gains 'published'

Revision ID: 0007
Revises: 0006
Create Date: 2026-09-21
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


CONSTRAINT = "ck_moderation_reviews_reason_for_rejection"
# snapshot of the constraint created by 0006
REASON_REQUIRED = r"decision <> 'rejected' OR (reason IS NOT NULL AND reason ~ '\S')"


def upgrade() -> None:
    # PostgreSQL 12 and up accept this inside a transaction as long as the new value is not
    # used in the same one — this migration only adds it
    op.execute("ALTER TYPE moderation_decision ADD VALUE IF NOT EXISTS 'published'")


def downgrade() -> None:
    # a value cannot be taken out of an enum, so the type is rebuilt without it. The rows the
    # upgrade made possible go with it: a downgrade cannot keep what the old schema cannot hold
    op.execute("DELETE FROM moderation_reviews WHERE decision = 'published'")
    # the check compares decision against a literal of the old type, so it has to go before
    # the column changes type and come back after
    op.drop_constraint(CONSTRAINT, "moderation_reviews", type_="check")
    op.execute("ALTER TYPE moderation_decision RENAME TO moderation_decision_old")
    op.execute("CREATE TYPE moderation_decision AS ENUM ('approved', 'rejected', 'hidden')")
    op.execute(
        "ALTER TABLE moderation_reviews ALTER COLUMN decision TYPE moderation_decision "
        "USING decision::text::moderation_decision"
    )
    op.execute("DROP TYPE moderation_decision_old")
    op.create_check_constraint(CONSTRAINT, "moderation_reviews", REASON_REQUIRED)
