import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models import Session


class SessionRead(BaseModel):
    """One device, as its owner sees it.

    The token is not here and never will be — not even a prefix of it. A list of devices is a
    screen people are told to check when something feels wrong, which makes it a screen an
    attacker reads too, and the only reason to put a fragment of a live credential on it would
    be to help somebody recognise their own laptop. The time and the browser do that.
    """

    model_config = ConfigDict(from_attributes=True)

    # the family rather than the row: renewing a token must not look like a new device
    id: uuid.UUID
    user_agent: str | None
    ip: str | None
    created_at: datetime
    last_seen_at: datetime
    # so the screen can say "this one" instead of making somebody guess
    current: bool = False

    @classmethod
    def of(cls, row: Session, *, current: bool) -> "SessionRead":
        return cls(
            id=row.family_id,
            user_agent=row.user_agent,
            ip=row.ip,
            created_at=row.created_at,
            last_seen_at=row.last_seen_at,
            current=current,
        )


class SessionListResponse(BaseModel):
    items: list[SessionRead]


class DeviceKeyRequest(BaseModel):
    """The public half of a key the browser keeps and cannot export.

    SPKI, base64 — what `crypto.subtle.exportKey("spki", ...)` produces once it has been
    through the usual dance into text.
    """

    public_key: str = Field(min_length=1, max_length=2048)
