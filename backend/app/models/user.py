import enum
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Index, String, text
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
        # nulls last, so accounts that never came back do not crowd out the ones that did
        Index("ix_users_last_login_at", text("last_login_at DESC NULLS LAST")),
    )

    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    # Not unique, and deliberately. Nobody checks that a number belongs to whoever typed it,
    # so a unique constraint on it was a way to take something from a stranger: type their
    # number into the registration form and they can no longer use their own. Indexed, because
    # the administrator's search reads it — see migration 0028.
    phone: Mapped[str | None] = mapped_column(String(32), index=True)
    # Null for an account that only ever signs in with a provider. A column insisting on a
    # value would have to be filled with something, and whatever that something was would be
    # a value somebody could try to guess against — see migration 0029.
    password_hash: Mapped[str | None] = mapped_column(String(255))
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
    # When the person last proved who they were. Written on a password login only: refresh
    # rotation happens on its own schedule and would turn this into "the token is alive".
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # A password somebody else chose is not a password. Set when an account is created from
    # the environment rather than by its owner, and cleared the moment they pick their own.
    must_change_password: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false"), nullable=False
    )

    business: Mapped["Business | None"] = relationship(
        back_populates="owner", cascade="all, delete-orphan"
    )

    @property
    def is_active(self) -> bool:
        """Whether the account may act at all. Asked on every authorized request, so that a
        block takes hold without waiting for an access token to run out."""
        return self.status is UserStatus.ACTIVE
