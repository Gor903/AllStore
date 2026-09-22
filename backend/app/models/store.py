import enum
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, String
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.business import Business

# the pattern below encodes the same bounds — keep the three in step
SUBDOMAIN_MIN_LENGTH = 3
SUBDOMAIN_MAX_LENGTH = 63
# a DNS label: lowercase, no leading or trailing hyphen
SUBDOMAIN_PATTERN = r"^[a-z0-9][a-z0-9-]{1,61}[a-z0-9]$"

COLOUR_PATTERN = r"^#[0-9a-f]{6}$"

# a theme is added here once the storefront can actually render it; until then an unknown
# id is refused rather than stored, so a seller cannot pick a look that does not exist
AVAILABLE_THEMES = frozenset({"default"})


class StoreStatus(enum.StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    BLOCKED = "blocked"


class Store(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "stores"
    __table_args__ = (
        # the subdomain routes every public request, so its shape is enforced at rest too
        CheckConstraint(f"subdomain ~ '{SUBDOMAIN_PATTERN}'", name="ck_stores_subdomain_format"),
    )

    # one business runs one storefront in the MVP, hence unique
    business_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("businesses.id", ondelete="CASCADE"), unique=True, index=True, nullable=False
    )
    subdomain: Mapped[str] = mapped_column(
        String(SUBDOMAIN_MAX_LENGTH), unique=True, index=True, nullable=False
    )
    logo_url: Mapped[str | None] = mapped_column(String(1024))
    banner_url: Mapped[str | None] = mapped_column(String(1024))
    # hex colours (#rrggbb); NULL means the theme default applies
    primary_color: Mapped[str | None] = mapped_column(String(7))
    secondary_color: Mapped[str | None] = mapped_column(String(7))
    # no themes table in the MVP: the id is the slug of a built-in theme
    theme_id: Mapped[str] = mapped_column(String(32), default="default", nullable=False)
    # a freshly created storefront stays draft until its business passes moderation
    status: Mapped[StoreStatus] = mapped_column(
        SAEnum(StoreStatus, name="store_status", values_callable=lambda e: [m.value for m in e]),
        default=StoreStatus.DRAFT,
        nullable=False,
    )

    business: Mapped["Business"] = relationship(back_populates="store")
