"""Proving that an address belongs to the person who typed it.

One table for both jobs, because they are the same job. Confirming the address an account
registered with and confirming the address it wants to move to differ only in which address is
written in `email` — the first time it matches what the account already has, the second time it
does not. A second table would have meant a second expiry, a second "used" flag and two places
to get the same rule wrong.

That is also what makes a pending address expressible without a column for it: an account is
waiting to move when it has a live row naming an address other than its own. The old address
keeps working until the new one answers, which is the point — somebody who mistypes their new
email must not be locked out of the account by it.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDPrimaryKeyMixin


class EmailVerification(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "email_verifications"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    # The address this row is about. Equal to the account's own when confirming what it
    # registered with; different when it is waiting to move.
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # Set when spent, and also when superseded: asking for a new link puts the old one out of
    # use, so a letter dug out of an old inbox cannot undo a later decision.
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
