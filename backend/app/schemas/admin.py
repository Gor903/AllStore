import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.models import AuditLog, UserRole
from app.schemas.auth import UserRead
from app.schemas.moderation import ModerationReason


class UserListResponse(BaseModel):
    items: list[UserRead]
    total: int
    limit: int
    offset: int


class RoleChangeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: UserRole


class BlockRequest(BaseModel):
    """Blocking takes a person's access away, so the record carries why."""

    model_config = ConfigDict(extra="forbid")

    reason: ModerationReason


class AuditLogRead(BaseModel):
    id: uuid.UUID
    action: str
    entity_type: str
    entity_id: uuid.UUID | None
    details: dict[str, Any]
    created_at: datetime
    # the email rather than the identifier: a journal is read by people
    actor_email: str | None

    @classmethod
    def from_entry(cls, entry: AuditLog) -> "AuditLogRead":
        return cls(
            id=entry.id,
            action=entry.action,
            entity_type=entry.entity_type,
            entity_id=entry.entity_id,
            details=entry.details,
            created_at=entry.created_at,
            actor_email=None if entry.actor is None else entry.actor.email,
        )


class AuditLogListResponse(BaseModel):
    items: list[AuditLogRead]
    total: int
    limit: int
    offset: int
