import enum
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, String
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.product import Product

CATEGORY_SLUG_MAX_LENGTH = 100
# lowercase words joined by single hyphens — the shape a catalogue URL segment may take
CATEGORY_SLUG_PATTERN = r"^[a-z0-9]+(-[a-z0-9]+)*$"


class CategoryStatus(enum.StrEnum):
    ACTIVE = "active"
    HIDDEN = "hidden"


class Category(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "categories"
    __table_args__ = (
        CheckConstraint(f"slug ~ '{CATEGORY_SLUG_PATTERN}'", name="ck_categories_slug_format"),
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # the public catalogue addresses a category by slug, so it is unique and stays url-safe
    slug: Mapped[str] = mapped_column(
        String(CATEGORY_SLUG_MAX_LENGTH), unique=True, index=True, nullable=False
    )
    # NULL marks a top-level category; the MVP tree is two levels deep
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("categories.id", ondelete="CASCADE"), index=True
    )
    # hidden keeps a category out of the catalogue without deleting the products filed under it
    status: Mapped[CategoryStatus] = mapped_column(
        SAEnum(
            CategoryStatus, name="category_status", values_callable=lambda e: [m.value for m in e]
        ),
        default=CategoryStatus.ACTIVE,
        nullable=False,
    )

    parent: Mapped["Category | None"] = relationship(
        back_populates="children", remote_side="Category.id"
    )
    children: Mapped[list["Category"]] = relationship(
        back_populates="parent", cascade="all, delete-orphan", order_by="Category.name"
    )
    products: Mapped[list["Product"]] = relationship(back_populates="category")
