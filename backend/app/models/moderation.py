import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Text, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.product import Product
    from app.models.user import User


class ModerationDecision(enum.StrEnum):
    APPROVED = "approved"
    REJECTED = "rejected"
    HIDDEN = "hidden"
    # a hide taken back: the product returns to the shelf on the same approval as before
    PUBLISHED = "published"


class ModerationReview(UUIDPrimaryKeyMixin, Base):
    """One verdict of one moderator. Append-only: a decision is never edited, only followed
    by another one, so the table carries created_at and no updated_at."""

    __tablename__ = "moderation_reviews"
    __table_args__ = (
        # a refusal without a reason is one the seller cannot act on; \S means at least one
        # character that is not whitespace, so a line of spaces does not pass for a reason
        CheckConstraint(
            r"decision <> 'rejected' OR (reason IS NOT NULL AND reason ~ '\S')",
            name="ck_moderation_reviews_reason_for_rejection",
        ),
    )

    product_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), index=True, nullable=False
    )
    # SET NULL: a moderator's account may go, the record of what they decided may not
    moderator_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    decision: Mapped[ModerationDecision] = mapped_column(
        SAEnum(
            ModerationDecision,
            name="moderation_decision",
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
    )
    reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    product: Mapped["Product"] = relationship(back_populates="reviews")
    moderator: Mapped["User | None"] = relationship()
