import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, EmailStr, Field, SecretStr, StringConstraints

from app.core.security import MAX_PASSWORD_LENGTH, MIN_PASSWORD_LENGTH
from app.models import BusinessStatus, UserRole, UserStatus

Password = Annotated[
    SecretStr, Field(min_length=MIN_PASSWORD_LENGTH, max_length=MAX_PASSWORD_LENGTH)
]
Phone = Annotated[str, StringConstraints(pattern=r"^\+?\d{6,20}$")]
Name = Annotated[str, StringConstraints(min_length=2, max_length=255, strip_whitespace=True)]


class _EmailOwner(BaseModel):
    email: EmailStr

    @property
    def normalized_email(self) -> str:
        """Addresses differing only in case are the same account — the database sees one form."""
        return self.email.strip().lower()


class BuyerRegisterRequest(_EmailOwner):
    password: Password
    phone: Phone | None = None


class SellerRegisterRequest(BuyerRegisterRequest):
    legal_name: Name
    display_name: Name


class LoginRequest(_EmailOwner):
    password: SecretStr


class PasswordResetRequest(_EmailOwner):
    pass


class PasswordResetConfirmRequest(BaseModel):
    token: str
    password: Password


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    phone: str | None
    role: UserRole
    status: UserStatus
    email_verified_at: datetime | None
    created_at: datetime


class BusinessRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    legal_name: str
    display_name: str
    description: str | None
    status: BusinessStatus
    created_at: datetime


class SellerRegisterResponse(BaseModel):
    user: UserRead
    business: BusinessRead


class MessageResponse(BaseModel):
    message: str
