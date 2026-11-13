"""What a seller may say about a product, and what a product says back.

The price is the field with consequences: it is money, so it is a `Decimal` with the column's
own precision rather than a float, and the schema refuses anything the column would round.

The read side carries one thing worth asserting beyond its shape. While a proposed change is
waiting to be judged, the product's own fields stay as the buyer knows them and the proposal
travels beside them — that is what keeps a live listing live while its edit is in a queue.
"""

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.models import ModerationStatus, ProductAvailability, PublicationStatus
from app.models.product import Product
from app.models.product_revision import ProductRevision, RevisionStatus
from app.schemas.product import ProductCreateRequest, ProductRead, ProductUpdateRequest

CATEGORY = uuid.uuid4()


def _created(**overrides: object) -> ProductCreateRequest:
    return ProductCreateRequest(
        **{"category_id": CATEGORY, "name": "Чашка", "price": Decimal("1500.00"), **overrides}
    )


def test_a_product_needs_a_category_a_name_and_a_price_and_nothing_else() -> None:
    """The stock and the availability have defaults, because a seller listing one thing they
    have in hand should not have to answer three questions to say so."""
    product = _created()

    assert product.stock_quantity == 0
    assert product.availability_status is ProductAvailability.IN_STOCK


@pytest.mark.parametrize("missing", ["category_id", "name", "price"])
def test_what_a_product_cannot_be_listed_without(missing: str) -> None:
    body = {"category_id": CATEGORY, "name": "Чашка", "price": Decimal("1500.00")}
    del body[missing]

    with pytest.raises(ValidationError):
        ProductCreateRequest(**body)


@pytest.mark.parametrize("name", ["", "   ", "\n"])
def test_whitespace_alone_is_not_a_name(name: str) -> None:
    """Trimmed before the length is counted, so a form full of spaces is an empty form."""
    with pytest.raises(ValidationError):
        _created(name=name)


def test_a_name_arrives_without_the_whitespace_around_it() -> None:
    assert _created(name="  Чашка  ").name == "Чашка"


@pytest.mark.parametrize("price", ["0", "0.01", "1500", "1500.50", "9999999999.99"])
def test_a_price_the_column_can_hold_is_taken(price: str) -> None:
    assert _created(price=Decimal(price)).price == Decimal(price)


@pytest.mark.parametrize(
    "price",
    [
        "-1",  # a debt is not a price
        "1500.555",  # more decimal places than the column keeps
        "99999999999.99",  # more digits than the column holds
    ],
)
def test_a_price_it_cannot_is_refused_rather_than_rounded(price: str) -> None:
    """Rounding money silently is how a shop ends up charging a different number than it
    showed. The column would do it; the schema says no first."""
    with pytest.raises(ValidationError):
        _created(price=Decimal(price))


def test_a_price_is_not_read_as_a_float() -> None:
    """0.1 + 0.2 is not 0.3, and a price is a thing somebody pays."""
    assert isinstance(_created(price=Decimal("1500.10")).price, Decimal)


@pytest.mark.parametrize("quantity", [-1, -1000])
def test_a_negative_stock_is_refused(quantity: int) -> None:
    with pytest.raises(ValidationError):
        _created(stock_quantity=quantity)


def test_a_field_nobody_declared_is_refused_rather_than_ignored() -> None:
    """A client sending `moderation_status` is a client trying to approve its own product,
    and dropping the field silently would make that look like it worked."""
    with pytest.raises(ValidationError):
        _created(moderation_status="approved")


@pytest.mark.parametrize("field", ["moderation_status", "publication_status"])
def test_a_seller_cannot_ask_for_their_own_verdict(field: str) -> None:
    """Neither on creation nor on an edit: those transitions belong to moderation."""
    assert field not in ProductUpdateRequest.model_fields
    assert field not in ProductCreateRequest.model_fields


def test_only_what_the_body_carries_changes() -> None:
    update = ProductUpdateRequest(price=Decimal("1600.00"))

    assert update.model_fields_set == {"price"}


def test_the_description_is_the_one_field_an_edit_may_clear() -> None:
    update = ProductUpdateRequest(description=None)

    assert update.description is None
    assert "description" in update.model_fields_set


@pytest.mark.parametrize("field", ["name", "price", "category_id", "stock_quantity"])
def test_a_null_anywhere_else_is_a_mistake_rather_than_an_intent(field: str) -> None:
    """A product with no name or no price is not a product, so `null` there is a client bug —
    and a client bug answered with a 422 is one somebody can find."""
    with pytest.raises(ValidationError, match="нельзя очистить"):
        ProductUpdateRequest(**{field: None})


def _product(**overrides: object) -> Product:
    product = Product(
        id=uuid.uuid4(),
        business_id=uuid.uuid4(),
        category_id=CATEGORY,
        name="Чашка",
        description=None,
        price=Decimal("1500.00"),
        currency="AMD",
        stock_quantity=1,
        availability_status=ProductAvailability.IN_STOCK,
        moderation_status=ModerationStatus.APPROVED,
        publication_status=PublicationStatus.PUBLISHED,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        **overrides,
    )
    product.images = []
    product.revisions = []
    return product


def _revision(status: RevisionStatus, **overrides: object) -> ProductRevision:
    return ProductRevision(
        id=uuid.uuid4(),
        name="Чашка с блюдцем",
        description=None,
        category_id=CATEGORY,
        status=status,
        created_at=datetime.now(UTC),
        **overrides,
    )


def test_a_product_with_nothing_pending_says_so() -> None:
    read = ProductRead.of(_product())

    assert read.pending_change is None
    assert read.change_rejection_reason is None


def test_a_proposed_change_travels_beside_the_product_rather_than_inside_it() -> None:
    """The buyer sees the name above while the seller waits on the one below. Writing the
    proposal into the product's own fields would publish an unjudged edit."""
    product = _product()
    product.revisions = [_revision(RevisionStatus.PENDING)]

    read = ProductRead.of(product)

    assert read.name == "Чашка"
    assert read.pending_change is not None
    assert read.pending_change.name == "Чашка с блюдцем"


def test_a_refused_change_is_told_to_the_seller_while_the_listing_stands() -> None:
    """Distinct from a refused product: this shop's listing is live and its edit was turned
    down, and the seller has no other way of being told that."""
    product = _product()
    product.revisions = [_revision(RevisionStatus.REJECTED, reason="Фото не то")]

    read = ProductRead.of(product)

    assert read.pending_change is None
    assert read.change_rejection_reason == "Фото не то"
