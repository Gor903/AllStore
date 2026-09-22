import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Text, text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.business import Business
    from app.models.product import Product
    from app.models.user import User

REASON_MAX_LENGTH = 1000

# exactly one subject: a complaint about "something" is not something anyone can act on
ONE_SUBJECT = "(product_id IS NULL) <> (business_id IS NULL)"
# a refusal to act has to say why, the same rule moderation already lives by
RESOLUTION_REASONED = (
    r"status <> 'dismissed' OR (resolution_reason IS NOT NULL AND resolution_reason ~ '\S')"
)


class ReportStatus(enum.StrEnum):
    OPEN = "open"
    # the complaint was acted on: the product came off the shelf, the shop went off the air
    UPHELD = "upheld"
    DISMISSED = "dismissed"


class Report(UUIDPrimaryKeyMixin, Base):
    """A complaint about a product or a shop.

    Every complaint is kept as its own row even when twenty people report the same thing:
    each is a separate fact, and twenty of them say something one does not. The moderator's
    queue groups them by subject, so the repetition informs rather than floods.

    A guest may complain, so the reporter is nullable — someone who has just been cheated is
    not going to register first.
    """

    __tablename__ = "reports"
    __table_args__ = (
        CheckConstraint(ONE_SUBJECT, name="ck_reports_one_subject"),
        CheckConstraint(RESOLUTION_REASONED, name="ck_reports_reason_for_dismissal"),
    )

    # SET NULL rather than CASCADE: losing the account must not erase the complaint
    reporter_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    product_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), index=True
    )
    business_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("businesses.id", ondelete="CASCADE"), index=True
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[ReportStatus] = mapped_column(
        SAEnum(ReportStatus, name="report_status", values_callable=lambda e: [m.value for m in e]),
        default=ReportStatus.OPEN,
        index=True,
        nullable=False,
    )
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    resolution_reason: Mapped[str | None] = mapped_column(Text)
    # clock_timestamp(), not now(): several complaints closed in one transaction must not
    # share a timestamp, the same reason the audit log gives
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("clock_timestamp()"), nullable=False
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    reporter: Mapped["User | None"] = relationship(foreign_keys=[reporter_user_id])
    moderator: Mapped["User | None"] = relationship(foreign_keys=[resolved_by])
    product: Mapped["Product | None"] = relationship()
    business: Mapped["Business | None"] = relationship()
