import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text, text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.category import Category
    from app.models.product import Product
    from app.models.user import User


class RevisionStatus(enum.StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    # replaced by a newer proposal before anybody judged it
    SUPERSEDED = "superseded"


class ProductRevision(UUIDPrimaryKeyMixin, Base):
    """A version of a product's moderated text, proposed and waiting to be judged.

    This table exists because of one rule: a buyer goes on seeing the last approved version
    while a change to it is being checked. Without it, editing an approved product took it
    off the shelf the moment the seller touched the name — the shop lost a listing for as
    long as the queue was busy, and the punishment for fixing a typo was the same as for
    being refused.

    So the products table holds what the public sees, and this one holds what has been
    proposed. Approving a revision copies it onto the product; refusing one leaves the
    product exactly as the buyer already knows it. Nothing is ever edited away: a superseded
    or refused proposal keeps its row, which is how "what did they try to publish in March"
    has an answer.

    Only the moderated fields are here. Price and stock change under the seller's own hand
    and always did — a moderator did not approve the price, and holding it hostage to a
    queue would make the shelf wrong rather than careful.
    """

    __tablename__ = "product_revisions"
    __table_args__ = (
        # a refusal without a reason is one the seller cannot act on
        CheckConstraint(
            r"status <> 'rejected' OR (reason IS NOT NULL AND reason ~ '\S')",
            name="ck_product_revisions_reason_for_rejection",
        ),
        # one proposal in the queue per product: a second edit replaces the first rather than
        # queueing beside it, so a moderator never has to guess which one is current
        Index(
            "uq_product_revisions_pending",
            "product_id",
            unique=True,
            postgresql_where=text("status = 'pending'"),
        ),
    )

    product_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    # RESTRICT, as on the product: removing a category must not take proposals with it
    category_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("categories.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[RevisionStatus] = mapped_column(
        SAEnum(
            RevisionStatus, name="revision_status", values_callable=lambda e: [m.value for m in e]
        ),
        default=RevisionStatus.PENDING,
        index=True,
        nullable=False,
    )
    # SET NULL: a moderator's account may go, the record of what they decided may not
    moderator_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("clock_timestamp()"), nullable=False
    )
    # when it stopped being pending, whoever or whatever ended it — a verdict or a newer
    # proposal that took its place
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    product: Mapped["Product"] = relationship(back_populates="revisions")
    category: Mapped["Category"] = relationship()
    moderator: Mapped["User | None"] = relationship()

    @property
    def is_pending(self) -> bool:
        return self.status is RevisionStatus.PENDING
