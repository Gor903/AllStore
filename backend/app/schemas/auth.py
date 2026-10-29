import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, EmailStr, Field, SecretStr, StringConstraints

from app.core.security import MAX_PASSWORD_LENGTH, MIN_PASSWORD_LENGTH
from app.models import BusinessStatus, UserRole, UserStatus
from app.models.business import Business as BusinessModel

Password = Annotated[
    SecretStr, Field(min_length=MIN_PASSWORD_LENGTH, max_length=MAX_PASSWORD_LENGTH)
]
Phone = Annotated[str, StringConstraints(pattern=r"^\+?\d{6,20}$")]
Name = Annotated[str, StringConstraints(min_length=2, max_length=255, strip_whitespace=True)]


class EmailOwner(BaseModel):
    email: EmailStr

    @property
    def normalized_email(self) -> str:
        """Addresses differing only in case are the same account — the database sees one form."""
        return self.email.strip().lower()


class BuyerRegisterRequest(EmailOwner):
    password: Password
    phone: Phone | None = None


class BusinessDetails(BaseModel):
    """What a shop has to say about itself before it can exist: who it is in law, and what it
    calls itself to buyers. Both are NOT NULL on the table, which is why no path can create a
    business without asking."""

    legal_name: Name
    display_name: Name


class SellerRegisterRequest(BuyerRegisterRequest, BusinessDetails):
    """Both halves at once, because a password registration can ask for both at once."""


class BusinessOnboardingRequest(BusinessDetails):
    """The half asked later, when the first half came from Google.

    Google tells us an address and a name and nothing a shop needs, so a seller who arrived
    that way has an account and no business — and until this is answered, nothing to sell
    from. The phone is here rather than on the account form for the same reason: nobody ever
    asked them for it.
    """

    phone: Phone | None = None


class LoginRequest(EmailOwner):
    password: SecretStr


class PasswordResetRequest(EmailOwner):
    pass


class PasswordResetConfirmRequest(BaseModel):
    token: str
    password: Password


class EmailChangeRequest(EmailOwner):
    """The login is proved with the password, the same way the password is."""

    current_password: SecretStr


class PasswordChangeRequest(BaseModel):
    """The current password is asked for even when the account owes a change: a session left
    open on somebody else's screen must not be enough to take the account over."""

    current_password: SecretStr
    password: Password


class TotpCodeRequest(BaseModel):
    """Six digits from an application, or one of the recovery codes.

    Loosely bounded on purpose: the two shapes differ, and refusing one of them here would
    mean the form could not accept it at all. What a code is worth is decided by
    `services/totp.py`, which knows which of the two it is looking at.
    """

    code: Annotated[str, StringConstraints(min_length=6, max_length=32, strip_whitespace=True)]


class TotpEnrolmentResponse(BaseModel):
    """Shown once. The secret is here as text as well as in the image, because a telephone
    that cannot photograph a screen is still a telephone somebody has to use."""

    secret: str
    uri: str
    qr: str


class TotpRecoveryResponse(BaseModel):
    """Also shown once, and said so on the screen: these are hashed on our side, so there is
    no later moment at which they can be read out again."""

    recovery_codes: list[str]


class TotpStatus(BaseModel):
    enabled: bool
    # whether this account may not sign in without one, which is a property of its role
    required: bool
    recovery_codes_left: int


class EmailConfirmRequest(BaseModel):
    """The token from the link, and nothing else: whoever opens it may be on a device that
    was never signed in, which is the ordinary case for a letter."""

    token: str


class VerifyRequest(BaseModel):
    """Only the password: the account is already known, this is about the moment."""

    password: SecretStr


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    phone: str | None
    role: UserRole
    status: UserStatus
    last_login_at: datetime | None
    # the client needs this to send the owner to the right screen, not to decide anything:
    # the refusal itself comes from the server on every other route
    must_change_password: bool
    email_verified_at: datetime | None
    created_at: datetime


class BusinessRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    legal_name: str
    display_name: str
    description: str | None
    status: BusinessStatus
    # Why the shop is where it is, when a moderator said why. A refusal the seller cannot
    # read is a refusal they cannot answer — and answering it is the whole point of
    # `rejected` being a separate status from `blocked`.
    #
    # Filled by `of` rather than read off the model: it comes from the verdict history, and
    # a field that fetched it by itself would make every answer carrying a business load it.
    status_reason: str | None = None
    created_at: datetime

    @classmethod
    def of(cls, business: BusinessModel) -> "BusinessRead":
        """For the callers that loaded the history — the seller's own cabinet."""
        return cls.model_validate(business).model_copy(
            update={"status_reason": business.latest_reason}
        )


class SellerRegisterResponse(BaseModel):
    user: UserRead
    business: BusinessRead


class MessageResponse(BaseModel):
    message: str
