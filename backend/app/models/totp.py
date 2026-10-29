"""The second factor: a shared secret, and a handful of ways back in without it.

Two tables because they expire differently. The secret is one per account and lives until
somebody removes it; a recovery code is one of ten, is spent the first time it is used, and
the row stays afterwards so that the same code cannot be spent twice.

Neither is stored as it was given out. The secret is encrypted rather than hashed, because
the server has to compute codes from it — see `core/vault.py` for what that costs and why it
is still not the same as storing it plainly. The recovery codes are hashed like any other
token: nothing ever needs them back, only the answer to "was this one of them".
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDPrimaryKeyMixin


class TotpCredential(UUIDPrimaryKeyMixin, Base):
    """One account's authenticator, confirmed or half-enrolled."""

    __tablename__ = "totp_credentials"

    # One per account: a second factor somebody has two of is a second factor they have lost
    # track of. Replacing it means removing this row and enrolling again.
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True, nullable=False
    )
    secret_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    # Until a code has been typed, the enrolment has not happened. Without this an account
    # could be locked behind a secret that never reached a phone — the row exists, the
    # authenticator does not, and nobody can get in.
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # The last step this account spent. A code is good for its step and the drift either
    # side, so without remembering which was used, one read over a shoulder works twice.
    last_used_step: Mapped[int | None] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class TotpRecoveryCode(UUIDPrimaryKeyMixin, Base):
    """One way back in for somebody whose phone is at the bottom of a lake.

    Handed out as a set, shown once, and spent one at a time. Rows for spent codes are kept:
    deleting them would make a used code indistinguishable from one that never existed, and
    the distinction is exactly what stops it being used again.
    """

    __tablename__ = "totp_recovery_codes"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    code_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
