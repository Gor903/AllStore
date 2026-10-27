import enum
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.contact import SocialLink
    from app.models.moderation import BusinessModerationReview
    from app.models.product import Product
    from app.models.store import Store
    from app.models.user import User


class BusinessStatus(enum.StrEnum):
    PENDING = "pending"
    ACTIVE = "active"
    # refused with a reason, and the seller may fix what was wrong and apply again. Distinct
    # from suspended and blocked: those are verdicts on a shop that was already admitted
    REJECTED = "rejected"
    SUSPENDED = "suspended"
    BLOCKED = "blocked"


class Business(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "businesses"

    # one seller owns one business in the MVP, hence unique
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True, nullable=False
    )
    legal_name: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[BusinessStatus] = mapped_column(
        SAEnum(
            BusinessStatus, name="business_status", values_callable=lambda e: [m.value for m in e]
        ),
        default=BusinessStatus.PENDING,
        nullable=False,
    )

    owner: Mapped["User"] = relationship(back_populates="business")
    store: Mapped["Store | None"] = relationship(
        back_populates="business", cascade="all, delete-orphan"
    )
    products: Mapped[list["Product"]] = relationship(
        back_populates="business", cascade="all, delete-orphan"
    )
    # ordered by the enum, so every storefront lists the ways to reach it in the same order
    social_links: Mapped[list["SocialLink"]] = relationship(
        back_populates="business", cascade="all, delete-orphan", order_by="SocialLink.platform"
    )
    # newest first: what matters is the verdict in force now
    reviews: Mapped[list["BusinessModerationReview"]] = relationship(
        back_populates="business",
        cascade="all, delete-orphan",
        order_by="BusinessModerationReview.created_at.desc()",
    )

    @property
    def latest_reason(self) -> str | None:
        """Why the shop is where it is, when somebody said why.

        Read from the loaded history rather than from a column of its own: the reason lives
        in the verdict that carries it, and two copies of it would be one too many — the same
        arrangement as Product.rejection_reason.

        Deliberately not named after the schema field it fills. `reviews` is a lazy
        relationship, and a property the response model would reach for by name would make
        every answer carrying a business load the history — including the catalogue, which
        loads one business per card and needs none of it.
        """
        return next((review.reason for review in self.reviews if review.reason), None)
