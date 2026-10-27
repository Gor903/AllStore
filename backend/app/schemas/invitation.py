import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr

from app.models import InvitationStatus, ModeratorInvitation
from app.schemas.auth import EmailOwner, Password


class InvitationCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr


class ModeratorRegisterRequest(EmailOwner):
    """The address is sent back along with the token on purpose.

    It is what binds the invitation to one person: a link forwarded to a colleague arrives
    with the colleague's address and stops working. Nothing else travels from the client —
    the role is not a field anyone may ask for.
    """

    model_config = ConfigDict(extra="forbid")

    token: str
    password: Password


class InvitationRead(BaseModel):
    id: uuid.UUID
    email: str
    status: InvitationStatus
    created_at: datetime
    expires_at: datetime
    used_at: datetime | None
    revoked_at: datetime | None
    # emails rather than identifiers: this list is read by a person
    created_by_email: str | None
    revoked_by_email: str | None

    @classmethod
    def from_invitation(cls, invitation: ModeratorInvitation) -> "InvitationRead":
        return cls(
            id=invitation.id,
            email=invitation.email,
            status=invitation.status,
            created_at=invitation.created_at,
            expires_at=invitation.expires_at,
            used_at=invitation.used_at,
            revoked_at=invitation.revoked_at,
            created_by_email=(
                None if invitation.created_by is None else invitation.created_by.email
            ),
            revoked_by_email=(
                None if invitation.revoked_by is None else invitation.revoked_by.email
            ),
        )


class InvitationCreated(BaseModel):
    """The one and only time the secret is readable.

    It is not stored in a form anyone can read back, so an administrator who loses this
    answer revokes the invitation and issues another one rather than looking it up.
    """

    invitation: InvitationRead
    token: str


class InvitationListResponse(BaseModel):
    items: list[InvitationRead]
    total: int
    limit: int
    offset: int
