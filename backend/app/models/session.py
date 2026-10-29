"""One device's hold on an account.

This replaces the pair of tokens ADR 1 chose — a short JWT the server could not withdraw, and
a long opaque one that could only be spent at `/auth/refresh`. The pair existed so that the
common case cost no database read, and it was paid for twice: every authorized route had to
re-read the account anyway to make a block take effect at once, so the saving never arrived;
and nothing in the frontend ever called `/auth/refresh`, so the long token sat unused while
people were signed out every fifteen minutes.

One opaque token, looked up here, is what both halves were trying to be.

Rotation survives the change because it is the only thing that notices a theft: a token that
comes back after it was replaced was used by two parties, and the whole family goes. A row
per rotation rather than a mutated one, so `replaced_by_id` can tell a replayed token from a
token nobody ever issued.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, Uuid, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDPrimaryKeyMixin


class AuthMethod(enum.StrEnum):
    """How the person proved who they were when this family began."""

    PASSWORD = "password"  # noqa: S105 — the name of a way in, not a way in


class Session(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "sessions"
    __table_args__ = (
        # the device list, newest first, and the revoke-everything sweep
        Index("ix_sessions_user_id_last_seen", "user_id", "last_seen_at"),
        # revoking one device means revoking its whole family
        Index("ix_sessions_family_id", "family_id"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    # Constant across every rotation, which is what makes "this device" a thing one can name.
    # A new sign-in starts a new family; renewing a token stays inside the old one.
    family_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    # set when this row is rotated away, so a replayed token is distinguishable from a forged one
    replaced_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("sessions.id", ondelete="SET NULL")
    )
    # The public half of a key the browser cannot export (stage 4). Null means the device
    # could not hold one, which is allowed and costs that session a shorter absolute life.
    device_public_key: Mapped[str | None] = mapped_column(Text)
    user_agent: Mapped[str | None] = mapped_column(String(255))
    # what the session looked like when it began, so a later request from somewhere else is
    # something the platform can notice rather than something it has no memory of
    ip: Mapped[str | None] = mapped_column(String(45))
    auth_method: Mapped[AuthMethod] = mapped_column(
        SAEnum(AuthMethod, name="auth_method", values_callable=lambda e: [m.value for m in e]),
        default=AuthMethod.PASSWORD,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    # Two clocks, because they answer different questions. The sliding one asks whether the
    # person is still around; the absolute one puts an end to a session however busy it is,
    # so a token stolen from an active account does not last forever.
    idle_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    absolute_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # when the person last proved the password again, for the actions that ask for it twice
    verified_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    # The newest proof this session has accepted from its device key. A proof no newer than
    # this one is a proof that has already been used, which is how a captured signature is
    # stopped from being worth capturing — see services/device_keys.py.
    last_proof_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_reason: Mapped[str | None] = mapped_column(String(255))
