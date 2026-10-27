import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models import AccountBlock
from app.schemas.moderation import ModerationReason


class BlockRequest(BaseModel):
    """Blocking takes a person's access away, so the record carries why."""

    model_config = ConfigDict(extra="forbid")

    reason: ModerationReason


class UnblockRequest(BaseModel):
    """Lifting a restriction needs no justification — the reason is offered, not demanded."""

    model_config = ConfigDict(extra="forbid")

    reason: ModerationReason | None = None


class AccountBlockRead(BaseModel):
    id: uuid.UUID
    reason: str
    created_at: datetime
    # emails rather than identifiers: a history is read by people
    actor_email: str | None
    revoked_at: datetime | None
    revoked_by_email: str | None
    revoke_reason: str | None
    in_force: bool

    @classmethod
    def from_block(cls, block: AccountBlock) -> "AccountBlockRead":
        return cls(
            id=block.id,
            reason=block.reason,
            created_at=block.created_at,
            actor_email=None if block.actor is None else block.actor.email,
            revoked_at=block.revoked_at,
            revoked_by_email=None if block.revoked_by is None else block.revoked_by.email,
            revoke_reason=block.revoke_reason,
            in_force=block.in_force,
        )


class AccountBlockListResponse(BaseModel):
    items: list[AccountBlockRead]
    total: int
    limit: int
    offset: int
