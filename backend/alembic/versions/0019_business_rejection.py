"""a business can be refused and apply again

Revision ID: 0019
Revises: 0018
Create Date: 2026-10-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0019"
down_revision: str | None = "0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

REASON_CONSTRAINT = "ck_business_moderation_reviews_reason_for_refusal"
# The same text as in app.models.moderation, now with the new verdict among the refusals.
#
# `decision::text` rather than the enum itself: PostgreSQL refuses to *use* an enum value
# added in the same transaction, and the constraint names one. Comparing the label as text
# asks nothing of the type and says exactly the same thing.
REASON_FOR_REFUSAL = (
    r"decision::text NOT IN ('rejected', 'suspended', 'blocked') "
    r"OR (reason IS NOT NULL AND reason ~ '\S')"
)


def upgrade() -> None:
    # PostgreSQL allows adding enum values inside a transaction as long as nothing uses them
    # in the same one; nothing here does
    op.execute("ALTER TYPE business_status ADD VALUE IF NOT EXISTS 'rejected' AFTER 'active'")
    op.execute("ALTER TYPE business_decision ADD VALUE IF NOT EXISTS 'rejected' AFTER 'approved'")
    op.execute("ALTER TYPE business_decision ADD VALUE IF NOT EXISTS 'resubmitted'")

    op.drop_constraint(REASON_CONSTRAINT, "business_moderation_reviews", type_="check")
    op.create_check_constraint(
        REASON_CONSTRAINT, "business_moderation_reviews", sa.text(REASON_FOR_REFUSAL)
    )


def downgrade() -> None:
    """The enum values stay.

    Removing a value from a PostgreSQL enum means rebuilding the type and every column that
    uses it, and any row already refused would have nothing to be. Leaving them costs an
    unused label; taking them away costs data.
    """
    op.drop_constraint(REASON_CONSTRAINT, "business_moderation_reviews", type_="check")
    op.create_check_constraint(
        REASON_CONSTRAINT,
        "business_moderation_reviews",
        sa.text(
            r"decision NOT IN ('suspended', 'blocked') "
            r"OR (reason IS NOT NULL AND reason ~ '\S')"
        ),
    )
