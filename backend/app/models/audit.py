import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, ForeignKey, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.user import User

ACTION_MAX_LENGTH = 64
ENTITY_TYPE_MAX_LENGTH = 32


class AuditLog(UUIDPrimaryKeyMixin, Base):
    """Who did what to whom, and when.

    Written by the services that carry out administrative actions, never edited afterwards:
    a record that can be corrected is not a record. Hence no `updated_at` and no
    TimestampMixin — there is nothing here that may be updated. The actor is kept even if
    the account is later deleted: the entry outlives the person, which is the point of a log.
    """

    __tablename__ = "audit_logs"

    # SET NULL rather than CASCADE: losing the actor must not erase what they did
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    # "user.role_changed", "user.blocked" — a noun and what happened to it
    action: Mapped[str] = mapped_column(String(ACTION_MAX_LENGTH), index=True, nullable=False)
    entity_type: Mapped[str] = mapped_column(String(ENTITY_TYPE_MAX_LENGTH), nullable=False)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(index=True)
    # the column is `metadata` as the data model names it; the attribute cannot be, because
    # SQLAlchemy keeps `metadata` on every declarative class for the table registry
    details: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, default=dict, nullable=False)

    # clock_timestamp(), not now(): now() is the time the transaction began, so two entries
    # written in one transaction would share a timestamp and the journal's order among them
    # would be decided by a random identifier
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("clock_timestamp()"), nullable=False
    )

    actor: Mapped["User | None"] = relationship()
