"""The product status machine, in memory.

The arrangement these tests pin down is the one the whole revision stage exists for: what a
buyer sees lives on the product, what has been proposed lives on a revision, and a verdict on
a proposal never takes away a place on the shelf that was already earned.
"""

import uuid

import pytest

from app.models import (
    ModerationStatus,
    Product,
    ProductRevision,
    PublicationStatus,
    RevisionStatus,
)
from app.services import moderation
from app.services.moderation import InvalidTransitionError

PENDING = ModerationStatus.PENDING
APPROVED = ModerationStatus.APPROVED
REJECTED = ModerationStatus.REJECTED
DRAFT = PublicationStatus.DRAFT
PUBLISHED = PublicationStatus.PUBLISHED
HIDDEN = PublicationStatus.HIDDEN

CATEGORY = uuid.uuid4()
OTHER_CATEGORY = uuid.uuid4()
REASON = "Фотография не соответствует товару"


def product(
    moderation_status: ModerationStatus,
    publication_status: PublicationStatus,
    name: str = "Кружка",
) -> Product:
    """Built in memory: the statuses are set by hand, the model defaults apply on insert."""
    return Product(
        id=uuid.uuid4(),
        name=name,
        description="Старое описание",
        category_id=CATEGORY,
        moderation_status=moderation_status,
        publication_status=publication_status,
    )


def proposal(
    item: Product,
    name: str = "Кружка",
    status: RevisionStatus = RevisionStatus.PENDING,
) -> ProductRevision:
    return ProductRevision(
        id=uuid.uuid4(),
        product_id=item.id,
        name=name,
        description="Новое описание",
        category_id=OTHER_CATEGORY,
        status=status,
    )


def test_the_first_approval_puts_the_product_on_the_shelf() -> None:
    item = product(PENDING, DRAFT)

    moderation.approve_revision(item, proposal(item))

    assert item.moderation_status is APPROVED
    assert item.publication_status is PUBLISHED


def test_approving_a_proposal_makes_it_what_the_buyer_sees() -> None:
    item = product(PENDING, DRAFT)

    moderation.approve_revision(item, proposal(item, name="Кружка керамическая"))

    assert item.name == "Кружка керамическая"
    assert item.description == "Новое описание"
    assert item.category_id == OTHER_CATEGORY


def test_the_first_refusal_keeps_the_product_off_the_shelf() -> None:
    item = product(PENDING, DRAFT)

    moderation.reject_revision(item, proposal(item), REASON)

    assert item.moderation_status is REJECTED
    assert item.publication_status is DRAFT


def test_a_refused_change_leaves_a_live_listing_exactly_where_it_was() -> None:
    """The point of the whole arrangement: a refusal costs nothing that was already earned."""
    item = product(APPROVED, PUBLISHED, name="Кружка")
    change = proposal(item, name="Кружка со скидкой 90%")

    moderation.reject_revision(item, change, REASON)

    assert item.moderation_status is APPROVED
    assert item.publication_status is PUBLISHED
    assert item.name == "Кружка"
    assert change.status is RevisionStatus.REJECTED
    assert change.reason == REASON


def test_an_approved_change_replaces_the_live_text_without_disturbing_the_shelf() -> None:
    item = product(APPROVED, PUBLISHED, name="Кружка")

    moderation.approve_revision(item, proposal(item, name="Кружка керамическая"))

    assert item.name == "Кружка керамическая"
    assert item.publication_status is PUBLISHED


def test_approving_a_change_does_not_undo_a_moderator_hiding_the_product() -> None:
    """A hide is a verdict of its own; an edit is not an appeal against it."""
    item = product(APPROVED, HIDDEN)

    moderation.approve_revision(item, proposal(item))

    assert item.publication_status is HIDDEN


@pytest.mark.parametrize(
    "status", [RevisionStatus.APPROVED, RevisionStatus.REJECTED, RevisionStatus.SUPERSEDED]
)
def test_a_proposal_is_judged_only_once(status: RevisionStatus) -> None:
    item = product(PENDING, DRAFT)
    decided = proposal(item, status=status)

    with pytest.raises(InvalidTransitionError):
        moderation.approve_revision(item, decided)
    with pytest.raises(InvalidTransitionError):
        moderation.reject_revision(item, decided, REASON)


def test_a_verdict_stamps_when_it_was_passed() -> None:
    item = product(PENDING, DRAFT)
    change = proposal(item)

    moderation.approve_revision(item, change)

    assert change.decided_at is not None


def test_a_superseded_proposal_is_closed_without_a_reason() -> None:
    item = product(APPROVED, PUBLISHED)
    change = proposal(item)

    moderation.supersede(change)

    assert change.status is RevisionStatus.SUPERSEDED
    assert change.reason is None
    assert change.decided_at is not None


def test_a_published_product_can_be_hidden() -> None:
    item = product(APPROVED, PUBLISHED)

    moderation.hide(item)

    assert item.publication_status is HIDDEN
    assert item.moderation_status is APPROVED


@pytest.mark.parametrize("publication", [DRAFT, HIDDEN])
def test_only_a_published_product_can_be_hidden(publication: PublicationStatus) -> None:
    with pytest.raises(InvalidTransitionError):
        moderation.hide(product(APPROVED, publication))


def test_a_hidden_product_goes_back_on_the_shelf() -> None:
    item = product(APPROVED, HIDDEN)

    moderation.publish(item)

    assert item.publication_status is PUBLISHED


@pytest.mark.parametrize("status", [PENDING, REJECTED])
def test_an_unapproved_product_is_never_published(status: ModerationStatus) -> None:
    with pytest.raises(InvalidTransitionError):
        moderation.publish(product(status, HIDDEN))


def test_publishing_what_is_not_hidden_is_refused() -> None:
    with pytest.raises(InvalidTransitionError):
        moderation.publish(product(APPROVED, PUBLISHED))


def test_archiving_takes_the_product_off_the_shelf_without_a_verdict() -> None:
    item = product(APPROVED, PUBLISHED)

    moderation.withdraw(item)

    assert item.publication_status is HIDDEN
    assert item.moderation_status is APPROVED
