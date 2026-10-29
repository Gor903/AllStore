"""An account's other way in: a provider, and who that provider says this is.

**Identity is the provider's subject, never the address.** Google's `sub` is stable and
belongs to one account forever; the email on it is a label the owner can change, and one
address can pass between people at a company. Keying on the address would mean that somebody
who acquires an old address acquires the account it once pointed at.

**Nothing is merged on a matching address.** Signing in with Google at an address that
already has a password account does not join them — it refuses, and says to sign in the
ordinary way and link from the settings. Joining them would mean anybody who can persuade a
provider to assert an address can take the account behind it.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDPrimaryKeyMixin


class IdentityProvider(enum.StrEnum):
    GOOGLE = "google"


class UserIdentity(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "user_identities"
    __table_args__ = (
        # One provider account opens one platform account. Without this, two of ours could
        # both claim the same Google subject and both would be right.
        UniqueConstraint("provider", "provider_subject", name="uq_identity_provider_subject"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    provider: Mapped[IdentityProvider] = mapped_column(
        SAEnum(
            IdentityProvider,
            name="identity_provider",
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
    )
    # what the provider calls this person, and the only thing here that is an identity
    provider_subject: Mapped[str] = mapped_column(String(255), nullable=False)
    # The address the provider asserted when this was linked. Kept for the person reading
    # their own settings — "linked to which Google account?" — and for nothing else: it is
    # not matched on, because an address is not an identity.
    email_at_link: Mapped[str] = mapped_column(String(320), nullable=False)
    linked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
