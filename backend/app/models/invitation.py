import enum
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.user import User


class InvitationStatus(enum.StrEnum):
    """Derived, never stored. Four columns already say everything this would, and a fifth
    one repeating them is a fifth one to forget to update."""

    PENDING = "pending"
    ACCEPTED = "accepted"
    REVOKED = "revoked"
    EXPIRED = "expired"


class ModeratorInvitation(UUIDPrimaryKeyMixin, Base):
    """A personal, one-time invitation to become a moderator.

    Moderators have no self-registration: the role judges other people's shops, so it is
    handed out by name rather than claimed. The secret lives in the invitee's mailbox and
    nowhere else — only its sha256 is here, as with every other token in this codebase.

    Bound to one address. A link forwarded to somebody else is a link that stops working,
    because the address it was issued for is checked against the one registering.
    """

    __tablename__ = "moderator_invitations"
    __table_args__ = (
        # one live invitation per address: re-inviting means revoking the old one first, so
        # "which link is valid" never has two answers
        Index(
            "uq_moderator_invitations_live",
            "email",
            unique=True,
            postgresql_where=text("used_at IS NULL AND revoked_at IS NULL"),
        ),
    )

    email: Mapped[str] = mapped_column(String(320), index=True, nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    # SET NULL: an administrator may hand over and move on, who invited whom stays
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("clock_timestamp()"), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    accepted_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )

    created_by: Mapped["User | None"] = relationship(foreign_keys=[created_by_user_id])
    accepted_user: Mapped["User | None"] = relationship(foreign_keys=[accepted_user_id])
    revoked_by: Mapped["User | None"] = relationship(foreign_keys=[revoked_by_user_id])

    @property
    def status(self) -> InvitationStatus:
        """Accepted and revoked outrank expiry: what became of the invitation is more
        interesting than the fact that its clock has since run out."""
        if self.used_at is not None:
            return InvitationStatus.ACCEPTED
        if self.revoked_at is not None:
            return InvitationStatus.REVOKED
        if self.expires_at <= datetime.now(UTC):
            return InvitationStatus.EXPIRED
        return InvitationStatus.PENDING
