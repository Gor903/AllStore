import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr

from app.models import BusinessCustomerBlock
from app.schemas.moderation import ModerationReason


class CustomerBlockRequest(BaseModel):
    """By address: that is how a seller knows the person they fell out with."""

    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    reason: ModerationReason


class CustomerBlockRead(BaseModel):
    id: uuid.UUID
    buyer_email: str
    reason: str
    created_at: datetime
    revoked_at: datetime | None
    revoked_by_email: str | None
    in_force: bool
    # named only on the staff screens, where the question is which shops barred this person
    store_name: str | None

    @classmethod
    def from_block(
        cls, block: BusinessCustomerBlock, *, with_store: bool = False
    ) -> "CustomerBlockRead":
        return cls(
            id=block.id,
            buyer_email=block.buyer.email,
            reason=block.reason,
            created_at=block.created_at,
            revoked_at=block.revoked_at,
            revoked_by_email=None if block.revoked_by is None else block.revoked_by.email,
            in_force=block.in_force,
            store_name=block.business.display_name if with_store else None,
        )


class CustomerBlockListResponse(BaseModel):
    items: list[CustomerBlockRead]
    total: int
    limit: int
    offset: int
