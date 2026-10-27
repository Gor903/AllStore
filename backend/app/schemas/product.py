import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.models import (
    ModerationStatus,
    Product,
    ProductAvailability,
    ProductRevision,
    PublicationStatus,
)
from app.models.product import PRICE_PRECISION, PRICE_SCALE

DESCRIPTION_MAX_LENGTH = 5000

# trimmed first, so whitespace alone is not a name
ProductName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]
ProductDescription = Annotated[
    str, StringConstraints(strip_whitespace=True, max_length=DESCRIPTION_MAX_LENGTH)
]
Price = Annotated[Decimal, Field(ge=0, max_digits=PRICE_PRECISION, decimal_places=PRICE_SCALE)]
StockQuantity = Annotated[int, Field(ge=0)]

# a PATCH may clear the description; a null in any other field is a mistake, not an intent
CLEARABLE_FIELDS = frozenset({"description"})


class ProductCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category_id: uuid.UUID
    name: ProductName
    description: ProductDescription | None = None
    price: Price
    stock_quantity: StockQuantity = 0
    availability_status: ProductAvailability = ProductAvailability.IN_STOCK


class ProductUpdateRequest(BaseModel):
    """Only the fields present in the body change — an absent field is left alone.

    Moderation and publication are not here on purpose: a seller must not be able to
    approve or publish their own product. Those transitions belong to moderation (этап 5).
    """

    model_config = ConfigDict(extra="forbid")

    category_id: uuid.UUID | None = None
    name: ProductName | None = None
    description: ProductDescription | None = None
    price: Price | None = None
    stock_quantity: StockQuantity | None = None
    availability_status: ProductAvailability | None = None

    @model_validator(mode="after")
    def _only_clearable_fields_accept_null(self) -> "ProductUpdateRequest":
        nulled = sorted(
            field
            for field in self.model_fields_set
            if getattr(self, field) is None and field not in CLEARABLE_FIELDS
        )
        if nulled:
            raise ValueError(f"Эти поля нельзя очистить: {', '.join(nulled)}")
        return self


class ProductImageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    image_url: str
    sort_order: int
    alt_text: str | None


class ProductChangeRead(BaseModel):
    """What the seller has proposed and a moderator has not judged yet.

    Separate from the product's own fields on purpose: while this is filled, the two differ,
    and the difference is the whole point — the buyer sees one and the seller is waiting on
    the other.
    """

    id: uuid.UUID
    name: str
    description: str | None
    category_id: uuid.UUID
    created_at: datetime

    @classmethod
    def of(cls, revision: ProductRevision) -> "ProductChangeRead":
        return cls(
            id=revision.id,
            name=revision.name,
            description=revision.description,
            category_id=revision.category_id,
            created_at=revision.created_at,
        )


class ProductRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    business_id: uuid.UUID
    category_id: uuid.UUID
    name: str
    description: str | None
    price: Decimal
    currency: str
    stock_quantity: int
    availability_status: ProductAvailability
    moderation_status: ModerationStatus
    publication_status: PublicationStatus
    # filled only while the product stands refused, see Product.rejection_reason
    rejection_reason: str | None
    # What the seller changed and a moderator has yet to judge. The fields above stay as the
    # buyer knows them while this is set — that is what keeps a live listing live.
    #
    # Filled by `of` rather than read off the model: the proposals are a lazy relationship,
    # and a field that fetched them by itself would make every answer carrying a product
    # load a history it has no use for.
    pending_change: ProductChangeRead | None = None
    # why the last proposed change was refused, while the product itself stands
    change_rejection_reason: str | None = None
    images: list[ProductImageRead]
    created_at: datetime
    updated_at: datetime

    @classmethod
    def of(cls, product: Product) -> "ProductRead":
        pending = product.pending_revision
        return cls.model_validate(product).model_copy(
            update={
                "pending_change": None if pending is None else ProductChangeRead.of(pending),
                "change_rejection_reason": product.change_rejection_reason,
            }
        )


class ProductListResponse(BaseModel):
    items: list[ProductRead]
    total: int
    limit: int
    offset: int
