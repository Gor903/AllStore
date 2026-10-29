"""a session remembers where it was, so it can notice being somewhere else

Revision ID: 0032
Revises: 0031
Create Date: 2026-10-30

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0032"
down_revision: str | None = "0031"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # a snapshot of the columns in app.models.session: a migration must not follow the model
    #
    # Both stay null until a geolocation source is configured, and null is the ordinary case
    # even then: most addresses resolve to nothing useful. Nothing anywhere treats an unknown
    # place as a suspicious one — see app/core/geo.py.
    op.add_column("sessions", sa.Column("country", sa.String(length=2), nullable=True))
    op.add_column("sessions", sa.Column("asn", sa.String(length=32), nullable=True))

    # Existing sessions are left blank rather than guessed at. A column filled with a place
    # nobody looked up would make the first comparison after this migration a comparison
    # against an invention, and the answer to that is a step-up somebody did not deserve.


def downgrade() -> None:
    op.drop_column("sessions", "asn")
    op.drop_column("sessions", "country")
