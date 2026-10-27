import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.user import User


class AccountBlock(UUIDPrimaryKeyMixin, Base):
    """One global ban on one account, and how it ended.

    `users.status` says whether a person may act right now; that is a single value and it is
    overwritten every time. This table is the memory behind it: who was barred, by whom, for
    what, when, and who lifted it. A second ban on the same account adds a row rather than
    editing the first, so the question "has this happened before" has an answer.

    Nothing here is ever deleted. `user_id` is RESTRICT rather than CASCADE precisely so that
    it cannot be: a ban that disappears with the account it was about is not a record.
    """

    __tablename__ = "account_blocks"
    __table_args__ = (
        # a ban nobody can read a reason for is one the person cannot answer; \S means at
        # least one non-whitespace character, so a line of spaces is not a reason
        CheckConstraint(r"reason ~ '\S'", name="ck_account_blocks_reason"),
        # one ban in force per account: two moderators deciding in the same moment produce
        # one row and one refusal, not two bans that each need lifting
        Index(
            "uq_account_blocks_in_force",
            "user_id",
            unique=True,
            postgresql_where=text("revoked_at IS NULL"),
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    # SET NULL: a moderator's account may go, the record of what they decided may not
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("clock_timestamp()"), nullable=False
    )

    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    # optional, unlike the reason for the ban: lifting a restriction needs no justification,
    # but the one who lifts it often has something to add
    revoke_reason: Mapped[str | None] = mapped_column(Text)

    user: Mapped["User"] = relationship(foreign_keys=[user_id])
    actor: Mapped["User | None"] = relationship(foreign_keys=[actor_user_id])
    revoked_by: Mapped["User | None"] = relationship(foreign_keys=[revoked_by_user_id])

    @property
    def in_force(self) -> bool:
        return self.revoked_at is None
