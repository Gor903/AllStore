import uuid
from datetime import datetime
from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, StringConstraints, model_validator

from app.models import Business, Product
from app.models.report import REASON_MAX_LENGTH
from app.repositories.reports import OpenSubject
from app.schemas.moderation import ModerationProductRead
from app.schemas.store import Subdomain

# trimmed first, so a line of spaces is not a complaint
ReportReason = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=REASON_MAX_LENGTH)
]


class ReportRequest(BaseModel):
    """Exactly one subject. A complaint about "something" is not one anyone can act on.

    A shop is named by its subdomain rather than by an identifier: that is what a visitor
    has in front of them, and the public storefront deliberately carries no internal ids.
    """

    model_config = ConfigDict(extra="forbid")

    product_id: uuid.UUID | None = None
    subdomain: Subdomain | None = None
    reason: ReportReason

    @model_validator(mode="after")
    def _one_subject(self) -> Self:
        if (self.product_id is None) == (self.subdomain is None):
            raise ValueError("Укажите либо товар, либо магазин")
        return self


class ReportAccepted(BaseModel):
    """Deliberately thin: the person who complained has no business knowing what became
    of the complaint, or how many others filed one."""

    id: uuid.UUID


class ReportedShopRead(BaseModel):
    display_name: str
    subdomain: str | None


class ReportedSubjectRead(BaseModel):
    """One line of the moderator's queue: what is complained about and what was said."""

    product: ModerationProductRead | None
    shop: ReportedShopRead | None
    business_id: uuid.UUID | None
    total: int
    last_at: datetime
    reasons: list[str]

    @classmethod
    def of(
        cls,
        subject: OpenSubject,
        products: dict[uuid.UUID, Product],
        businesses: dict[uuid.UUID, Business],
    ) -> "ReportedSubjectRead":
        product = None if subject.product_id is None else products.get(subject.product_id)
        business = None if subject.business_id is None else businesses.get(subject.business_id)
        return cls(
            product=None if product is None else ModerationProductRead.from_product(product),
            shop=(
                None
                if business is None
                else ReportedShopRead(
                    display_name=business.display_name,
                    subdomain=None if business.store is None else business.store.subdomain,
                )
            ),
            business_id=subject.business_id,
            total=subject.total,
            last_at=subject.last_at,
            reasons=subject.reasons,
        )


class ReportQueueResponse(BaseModel):
    items: list[ReportedSubjectRead]
    total: int
    limit: int
    offset: int


class ReportResolutionResponse(BaseModel):
    """How many complaints the one verdict closed — twenty about one product is one act."""

    closed: int
