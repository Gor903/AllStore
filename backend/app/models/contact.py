import enum
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, String, UniqueConstraint
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.business import Business


class ContactPlatform(enum.StrEnum):
    """Declaration order is display order: a buyer sees the ways to call before the profiles."""

    PHONE = "phone"
    WHATSAPP = "whatsapp"
    TELEGRAM = "telegram"
    VIBER = "viber"
    INSTAGRAM = "instagram"
    FACEBOOK = "facebook"


# the platforms addressed by a phone number rather than by a handle
PHONE_PLATFORMS = frozenset(
    {ContactPlatform.PHONE, ContactPlatform.WHATSAPP, ContactPlatform.VIBER}
)

VALUE_MAX_LENGTH = 64


class SocialLink(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A way for a buyer to reach the seller. Public by its nature: the seller adds an entry
    here precisely so that it is shown. Account data — the login email, the phone of the user
    record, the legal name — lives elsewhere and never turns into a contact by itself."""

    __tablename__ = "social_links"
    __table_args__ = (
        # one entry per platform: a shop has one WhatsApp, and the settings form has one field
        UniqueConstraint("business_id", "platform", name="uq_social_links_business_platform"),
        CheckConstraint(r"value ~ '\S'", name="ck_social_links_value_not_blank"),
    )

    business_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("businesses.id", ondelete="CASCADE"), index=True, nullable=False
    )
    platform: Mapped[ContactPlatform] = mapped_column(
        SAEnum(
            ContactPlatform, name="contact_platform", values_callable=lambda e: [m.value for m in e]
        ),
        nullable=False,
    )
    # a number in E.164 or a handle — never a URL: the address is derived from it per platform,
    # so a stored value cannot send a buyer somewhere the platform did not intend
    value: Mapped[str] = mapped_column(String(VALUE_MAX_LENGTH), nullable=False)

    business: Mapped["Business"] = relationship(back_populates="social_links")
