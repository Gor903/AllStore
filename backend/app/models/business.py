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
