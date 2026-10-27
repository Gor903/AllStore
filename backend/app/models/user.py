import enum
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Index, String, text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.business import Business


class UserRole(enum.StrEnum):
    BUYER = "buyer"
    SELLER = "seller"
    MODERATOR = "moderator"
    ADMIN = "admin"


class UserStatus(enum.StrEnum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    BLOCKED = "blocked"


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"
    __table_args__ = (
        # One administrator, enforced where a race cannot argue with it. Every other guard on
        # the role hierarchy is a check in Python, and two requests can pass the same check in
        # the same moment; this index is the one that cannot be raced.
        Index(
            "uq_users_single_admin",
            "role",
            unique=True,
            postgresql_where=text("role = 'admin'"),
        ),
    )

    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    # phone is optional but can only be taken once — Postgres allows many NULLs under UNIQUE
    phone: Mapped[str | None] = mapped_column(String(32), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        SAEnum(UserRole, name="user_role", values_callable=lambda e: [m.value for m in e]),
        default=UserRole.BUYER,
        nullable=False,
    )
    status: Mapped[UserStatus] = mapped_column(
        SAEnum(UserStatus, name="user_status", values_callable=lambda e: [m.value for m in e]),
        default=UserStatus.ACTIVE,
        nullable=False,
    )
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    business: Mapped["Business | None"] = relationship(
        back_populates="owner", cascade="all, delete-orphan"
    )

    @property
    def is_active(self) -> bool:
        """Whether the account may act at all. Asked on every authorized request, so that a
        block takes hold without waiting for an access token to run out."""
        return self.status is UserStatus.ACTIVE
