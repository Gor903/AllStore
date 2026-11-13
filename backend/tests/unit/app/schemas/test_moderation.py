"""What a moderator is shown, and what they have to say to decide anything.

Two things are asserted here. A refusal carries a reason, because a refusal the seller cannot
act on is not a refusal — and a line of spaces is not a reason.

And the queue can tell the two kinds of work apart. A product nobody has seen and a change to a
listing already on the shelf look alike in a list and mean different things: refusing the first
keeps a shelf empty, refusing the second leaves a live listing exactly as the buyer knows it.
`is_change` is what the screen reads to say which it is looking at.
"""

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.models import (
    Business,
    BusinessDecision,
    BusinessModerationReview,
    BusinessStatus,
    Category,
    ModerationStatus,
    Product,
    ProductAvailability,
    PublicationStatus,
    Store,
    StoreStatus,
)
from app.models.product_revision import ProductRevision, RevisionStatus
from app.schemas.moderation import (
    REASON_MAX_LENGTH,
    BusinessReviewRead,
    ModerationProductRead,
    ModerationReasonRequest,
)

CATEGORY = uuid.uuid4()


@pytest.mark.parametrize("reason", ["Фото не то", "  Фото не то  ", "ч" * REASON_MAX_LENGTH])
def test_a_verdict_carries_the_reason_it_was_given_for(reason: str) -> None:
    assert ModerationReasonRequest(reason=reason).reason == reason.strip()


@pytest.mark.parametrize("reason", ["", "   ", "\n", "ч" * (REASON_MAX_LENGTH + 1)])
def test_something_the_seller_could_not_act_on_is_not_a_reason(reason: str) -> None:
    """Trimmed before the length is counted, so a line of spaces is an empty form."""
    with pytest.raises(ValidationError):
        ModerationReasonRequest(reason=reason)


def test_a_verdict_takes_nothing_but_a_reason() -> None:
    """`extra="forbid"`: a client that also sent a status would be asking to set the verdict
    itself, and dropping that field quietly would make the attempt look like it worked."""
    body: dict[str, object] = {"reason": "Фото не то", "moderation_status": "approved"}

    with pytest.raises(ValidationError):
        ModerationReasonRequest(**body)


def _product(status: ModerationStatus, *, pending: bool) -> Product:
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
        moderation_status=status,
        publication_status=PublicationStatus.PUBLISHED,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    product.images = []
    product.category = Category(id=CATEGORY, name="Посуда")
    product.business = Business(
        id=product.business_id,
        legal_name="ООО Ромашка",
        display_name="Ромашка",
        description=None,
        status=BusinessStatus.ACTIVE,
        created_at=datetime.now(UTC),
    )
    product.business.store = Store(
        id=uuid.uuid4(),
        business_id=product.business_id,
        subdomain="cups",
        theme_id="default",
        status=StoreStatus.ACTIVE,
        created_at=datetime.now(UTC),
    )
    revision = ProductRevision(
        id=uuid.uuid4(),
        name="Чашка с блюдцем",
        description=None,
        category_id=CATEGORY,
        status=RevisionStatus.PENDING,
        created_at=datetime.now(UTC),
    )
    revision.category = Category(id=CATEGORY, name="Посуда")
    product.revisions = [revision] if pending else []
    return product


def test_a_moderator_is_given_names_rather_than_identifiers() -> None:
    """Nobody can judge a category and a shop that arrive as uuids."""
    read = ModerationProductRead.from_product(_product(ModerationStatus.PENDING, pending=True))

    assert read.category_name == "Посуда"
    assert read.seller_name == "Ромашка"
    assert read.subdomain == "cups"


def test_a_product_nobody_has_approved_is_not_a_change() -> None:
    read = ModerationProductRead.from_product(_product(ModerationStatus.PENDING, pending=True))

    assert read.is_change is False
    assert read.proposed is not None
    assert read.proposed.name == "Чашка с блюдцем"
    assert read.proposed.category_name == "Посуда"


def test_an_edit_to_something_already_on_the_shelf_is() -> None:
    """A refusal means very different things in the two cases, and so does an approval."""
    read = ModerationProductRead.from_product(_product(ModerationStatus.APPROVED, pending=True))

    assert read.is_change is True


def test_what_the_buyer_sees_travels_beside_what_is_being_judged() -> None:
    """For a product nobody has approved the two are the same; for a change to a live listing
    they differ, and the moderator is deciding whether to replace one with the other."""
    read = ModerationProductRead.from_product(_product(ModerationStatus.APPROVED, pending=True))

    assert read.name == "Чашка"
    assert read.proposed is not None
    assert read.proposed.name == "Чашка с блюдцем"


def test_a_shop_with_no_storefront_yet_says_so_rather_than_breaking_the_queue() -> None:
    product = _product(ModerationStatus.PENDING, pending=True)
    product.business.store = None

    read = ModerationProductRead.from_product(product)

    assert read.subdomain is None


def _applicant(*, with_store: bool) -> Business:
    business = Business(
        id=uuid.uuid4(),
        legal_name="ООО Ромашка",
        display_name="Ромашка",
        description=None,
        status=BusinessStatus.PENDING,
        created_at=datetime.now(UTC),
    )
    business.store = (
        Store(
            id=uuid.uuid4(),
            business_id=business.id,
            subdomain="cups",
            theme_id="default",
            status=StoreStatus.ACTIVE,
            created_at=datetime.now(UTC),
        )
        if with_store
        else None
    )
    business.reviews = []
    return business


def test_an_applicant_carries_the_address_their_shop_would_answer_at() -> None:
    review = BusinessReviewRead.from_business(_applicant(with_store=True))

    assert review.subdomain == "cups"
    assert review.store_status is StoreStatus.ACTIVE


def test_an_applicant_with_no_storefront_is_a_valid_applicant() -> None:
    review = BusinessReviewRead.from_business(_applicant(with_store=False))

    assert review.subdomain is None
    assert review.store_status is None


def test_an_applicant_carries_what_was_already_decided_about_them() -> None:
    """Somebody refused once and applying again is a different case from somebody nobody has
    looked at yet, and the queue has no way to tell them apart without the history."""
    business = _applicant(with_store=False)
    business.reviews = [
        BusinessModerationReview(
            decision=BusinessDecision.REJECTED,
            reason="Нет документов",
            created_at=datetime.now(UTC),
        )
    ]

    review = BusinessReviewRead.from_business(business)

    assert [entry.decision for entry in review.history] == [BusinessDecision.REJECTED]
    assert review.history[0].reason == "Нет документов"


def test_an_applicant_nobody_has_looked_at_has_an_empty_history() -> None:
    assert BusinessReviewRead.from_business(_applicant(with_store=False)).history == []
