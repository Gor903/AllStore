import enum
import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.moderation import ModerationDecision

if TYPE_CHECKING:
    from app.models.business import Business
    from app.models.category import Category
    from app.models.moderation import ModerationReview
    from app.models.product_revision import ProductRevision

# a price is money, never a float: Numeric keeps the minor units exact
PRICE_PRECISION = 12
PRICE_SCALE = 2
DEFAULT_CURRENCY = "AMD"
# ISO 4217 alphabetic code
CURRENCY_PATTERN = r"^[A-Z]{3}$"


class ProductAvailability(enum.StrEnum):
    IN_STOCK = "in_stock"
    OUT_OF_STOCK = "out_of_stock"


class ModerationStatus(enum.StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class PublicationStatus(enum.StrEnum):
    DRAFT = "draft"
    PUBLISHED = "published"
    HIDDEN = "hidden"


class Product(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "products"
    __table_args__ = (
        CheckConstraint("price >= 0", name="ck_products_price_non_negative"),
        CheckConstraint("stock_quantity >= 0", name="ck_products_stock_non_negative"),
        CheckConstraint(f"currency ~ '{CURRENCY_PATTERN}'", name="ck_products_currency_format"),
    )

    # the tenant key: every query for product data filters on it
    business_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("businesses.id", ondelete="CASCADE"), index=True, nullable=False
    )
    # RESTRICT: removing a category must not silently take its products with it
    category_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("categories.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    price: Mapped[Decimal] = mapped_column(Numeric(PRICE_PRECISION, PRICE_SCALE), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default=DEFAULT_CURRENCY, nullable=False)
    stock_quantity: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    availability_status: Mapped[ProductAvailability] = mapped_column(
        SAEnum(
            ProductAvailability,
            name="product_availability",
            values_callable=lambda e: [m.value for m in e],
        ),
        default=ProductAvailability.IN_STOCK,
        nullable=False,
    )
    # a new product is invisible until a moderator approves it (этап 5), hence pending + draft
    moderation_status: Mapped[ModerationStatus] = mapped_column(
        SAEnum(
            ModerationStatus,
            name="moderation_status",
            values_callable=lambda e: [m.value for m in e],
        ),
        default=ModerationStatus.PENDING,
        index=True,
        nullable=False,
    )
    publication_status: Mapped[PublicationStatus] = mapped_column(
        SAEnum(
            PublicationStatus,
            name="publication_status",
            values_callable=lambda e: [m.value for m in e],
        ),
        default=PublicationStatus.DRAFT,
        index=True,
        nullable=False,
    )

    # a seller removes a product by archiving it: the images, and later the moderation verdict
    # and the order lines, keep the row they point at
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    business: Mapped["Business"] = relationship(back_populates="products")
    category: Mapped["Category"] = relationship(back_populates="products")
    images: Mapped[list["ProductImage"]] = relationship(
        back_populates="product",
        cascade="all, delete-orphan",
        order_by="ProductImage.sort_order",
    )
    # newest first: what the seller needs is the verdict that is in force now
    reviews: Mapped[list["ModerationReview"]] = relationship(
        back_populates="product",
        cascade="all, delete-orphan",
        order_by="ModerationReview.created_at.desc()",
    )
    # newest first, same reason: what was proposed last is what is being judged
    revisions: Mapped[list["ProductRevision"]] = relationship(
        back_populates="product",
        cascade="all, delete-orphan",
        order_by="ProductRevision.created_at.desc()",
    )

    @property
    def pending_revision(self) -> "ProductRevision | None":
        """The change waiting to be judged, if the seller has proposed one.

        At most one exists: a unique partial index on `status = 'pending'` says so, which is
        what lets a moderator act on "the product" without being asked which proposal.
        """
        return next((revision for revision in self.revisions if revision.is_pending), None)

    @property
    def change_rejection_reason(self) -> str | None:
        """Why the last proposed change was refused, while the product itself stands.

        Distinct from `rejection_reason`: that one is about a product that never made it
        onto the shelf. This one is about a shop whose listing is still live and whose edit
        was turned down — a case the seller has no other way of being told about.
        """
        from app.models.product_revision import RevisionStatus

        latest = next(
            (
                revision
                for revision in self.revisions
                if revision.status in (RevisionStatus.APPROVED, RevisionStatus.REJECTED)
            ),
            None,
        )
        if latest is None or latest.status is not RevisionStatus.REJECTED:
            return None
        return latest.reason

    @property
    def rejection_reason(self) -> str | None:
        """What the seller has to act on. Empty while the product has not been refused.

        Reads the loaded history rather than a column of its own: the reason lives in the
        verdict that carries it, and two copies of it would be one too many.
        """
        if self.moderation_status is not ModerationStatus.REJECTED:
            return None
        return next(
            (
                review.reason
                for review in self.reviews
                if review.decision is ModerationDecision.REJECTED
            ),
            None,
        )


class ProductImage(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "product_images"
    __table_args__ = (
        CheckConstraint("sort_order >= 0", name="ck_product_images_sort_order_non_negative"),
    )

    product_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), index=True, nullable=False
    )
    image_url: Mapped[str] = mapped_column(String(1024), nullable=False)
    # position in the gallery; the lowest one is the cover
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    alt_text: Mapped[str | None] = mapped_column(String(255))

    product: Mapped["Product"] = relationship(back_populates="images")
