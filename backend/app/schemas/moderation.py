import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints

from app.models import Business, BusinessStatus, StoreStatus

REASON_MAX_LENGTH = 1000

# trimmed first, so a line of spaces is not a reason
ModerationReason = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=REASON_MAX_LENGTH)
]


class ModerationReasonRequest(BaseModel):
    """A refusal the seller cannot act on is not a refusal, so the reason is required."""

    model_config = ConfigDict(extra="forbid")

    reason: ModerationReason


class BusinessReviewRead(BaseModel):
    """What a moderator needs to judge an applicant, storefront address included."""

    id: uuid.UUID
    legal_name: str
    display_name: str
    description: str | None
    status: BusinessStatus
    subdomain: str | None
    store_status: StoreStatus | None
    created_at: datetime

    @classmethod
    def from_business(cls, business: Business) -> "BusinessReviewRead":
        store = business.store
        return cls(
            id=business.id,
            legal_name=business.legal_name,
            display_name=business.display_name,
            description=business.description,
            status=business.status,
            subdomain=None if store is None else store.subdomain,
            store_status=None if store is None else store.status,
            created_at=business.created_at,
        )


class BusinessListResponse(BaseModel):
    items: list[BusinessReviewRead]
    total: int
    limit: int
    offset: int
