import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.business import Business
    from app.models.user import User


class BusinessCustomerBlock(UUIDPrimaryKeyMixin, Base):
    """A seller barring one buyer from one shop.

    Deliberately not the same thing as `account_blocks`, and deliberately not reachable from
    it. A seller may decide who is welcome in their own shop; they have no say over whether
    that person uses the rest of the platform. So this never touches `users.status` — the
    buyer goes on browsing, buying and complaining everywhere else, and only this one shop
    stops answering them.

    Enforced where visibility is decided rather than in each route: the public catalogue
    filter takes the viewer into account (see `repositories/catalog.py`), so the shop vanishes
    from listings, from search and from a saved link all at once, instead of in whichever
    places somebody remembered.
    """

    __tablename__ = "business_customer_blocks"
    __table_args__ = (
        CheckConstraint(r"reason ~ '\S'", name="ck_business_customer_blocks_reason"),
        # one block in force per shop-and-buyer pair, so lifting it is one action
        Index(
            "uq_business_customer_blocks_in_force",
            "business_id",
            "buyer_user_id",
            unique=True,
            postgresql_where=text("revoked_at IS NULL"),
        ),
    )

    # RESTRICT on both: this is a record of a decision, and a record that disappears with
    # what it is about is not one
    business_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("businesses.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    buyer_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    # the owner today; SET NULL because the shop may change hands and the decision stands
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("clock_timestamp()"), nullable=False
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )

    business: Mapped["Business"] = relationship()
    buyer: Mapped["User"] = relationship(foreign_keys=[buyer_user_id])
    created_by: Mapped["User | None"] = relationship(foreign_keys=[created_by_user_id])
    revoked_by: Mapped["User | None"] = relationship(foreign_keys=[revoked_by_user_id])

    @property
    def in_force(self) -> bool:
        return self.revoked_at is None
