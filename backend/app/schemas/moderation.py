import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints

from app.models import (
    Business,
    BusinessDecision,
    BusinessModerationReview,
    BusinessStatus,
    Product,
    StoreStatus,
)
from app.schemas.product import ProductRead

REASON_MAX_LENGTH = 1000

# trimmed first, so a line of spaces is not a reason
ModerationReason = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=REASON_MAX_LENGTH)
]


class ModerationReasonRequest(BaseModel):
    """A refusal the seller cannot act on is not a refusal, so the reason is required."""

    model_config = ConfigDict(extra="forbid")

    reason: ModerationReason


class ModerationProductRead(ProductRead):
    """The seller's view of a product plus who and what stands behind it — a moderator
    cannot judge a category and a shop that arrive as identifiers."""

    category_name: str
    seller_name: str
    subdomain: str | None

    @classmethod
    def from_product(cls, product: Product) -> "ModerationProductRead":
        store = product.business.store
        return cls(
            **ProductRead.model_validate(product).model_dump(),
            category_name=product.category.name,
            seller_name=product.business.display_name,
            subdomain=None if store is None else store.subdomain,
        )


class ModerationProductListResponse(BaseModel):
    items: list[ModerationProductRead]
    total: int
    limit: int
    offset: int


class BusinessDecisionRead(BaseModel):
    """One verdict that was passed on this applicant, and why."""

    decision: BusinessDecision
    reason: str | None
    created_at: datetime

    @classmethod
    def of(cls, review: BusinessModerationReview) -> "BusinessDecisionRead":
        return cls(decision=review.decision, reason=review.reason, created_at=review.created_at)


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
    # newest first: somebody refused once and now applying again is a different case from
    # somebody nobody has looked at yet, and the queue has no way to tell without this
    history: list[BusinessDecisionRead]

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
            history=[BusinessDecisionRead.of(review) for review in business.reviews],
        )


class BusinessListResponse(BaseModel):
    items: list[BusinessReviewRead]
    total: int
    limit: int
    offset: int
