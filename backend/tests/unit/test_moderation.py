import pytest

from app.models import ModerationStatus, Product, PublicationStatus
from app.services import moderation
from app.services.moderation import InvalidTransitionError

PENDING = ModerationStatus.PENDING
APPROVED = ModerationStatus.APPROVED
REJECTED = ModerationStatus.REJECTED
DRAFT = PublicationStatus.DRAFT
PUBLISHED = PublicationStatus.PUBLISHED
HIDDEN = PublicationStatus.HIDDEN


def product(moderation_status: ModerationStatus, publication_status: PublicationStatus) -> Product:
    """Built in memory: the statuses are set by hand, the model defaults apply on insert."""
    return Product(moderation_status=moderation_status, publication_status=publication_status)


def test_approving_puts_the_product_on_the_shelf() -> None:
    item = product(PENDING, DRAFT)

    moderation.approve(item)

    assert item.moderation_status is APPROVED
    assert item.publication_status is PUBLISHED


def test_rejecting_keeps_the_product_off_the_shelf() -> None:
    item = product(PENDING, DRAFT)

    moderation.reject(item)

    assert item.moderation_status is REJECTED
    assert item.publication_status is DRAFT


@pytest.mark.parametrize("verdict", [APPROVED, REJECTED])
def test_a_verdict_is_passed_only_once(verdict: ModerationStatus) -> None:
    """A second approve or reject would overwrite a decision instead of following it."""
    item = product(verdict, DRAFT)

    with pytest.raises(InvalidTransitionError):
        moderation.approve(item)
    with pytest.raises(InvalidTransitionError):
        moderation.reject(item)


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


@pytest.mark.parametrize("verdict", [PENDING, REJECTED])
def test_nothing_is_published_without_approval(verdict: ModerationStatus) -> None:
    """The rule the whole machine exists for: publish never runs ahead of moderation."""
    item = product(verdict, HIDDEN)

    with pytest.raises(InvalidTransitionError):
        moderation.publish(item)

    assert item.publication_status is HIDDEN


@pytest.mark.parametrize("publication", [DRAFT, PUBLISHED])
def test_only_a_hidden_product_is_republished(publication: PublicationStatus) -> None:
    with pytest.raises(InvalidTransitionError):
        moderation.publish(product(APPROVED, publication))


@pytest.mark.parametrize(
    ("verdict", "publication"), [(REJECTED, DRAFT), (APPROVED, PUBLISHED), (APPROVED, HIDDEN)]
)
def test_the_seller_returns_the_product_to_the_queue(
    verdict: ModerationStatus, publication: PublicationStatus
) -> None:
    item = product(verdict, publication)

    moderation.submit_for_review(item)

    assert item.moderation_status is PENDING
    assert item.publication_status is DRAFT


def test_a_product_already_in_the_queue_is_not_resubmitted() -> None:
    item = product(PENDING, DRAFT)

    with pytest.raises(InvalidTransitionError):
        moderation.submit_for_review(item)


@pytest.mark.parametrize("verdict", [PENDING, APPROVED, REJECTED])
def test_withdrawing_takes_the_product_off_the_shelf_whatever_the_verdict(
    verdict: ModerationStatus,
) -> None:
    """Archiving is the seller's own doing, so the verdict stands as it was."""
    item = product(verdict, PUBLISHED)

    moderation.withdraw(item)

    assert item.publication_status is HIDDEN
    assert item.moderation_status is verdict


def test_an_invalid_transition_is_a_conflict_with_a_readable_message() -> None:
    with pytest.raises(InvalidTransitionError) as raised:
        moderation.approve(product(APPROVED, PUBLISHED))

    assert raised.value.status_code == 409
    assert raised.value.code == "invalid_transition"
    assert raised.value.message == "Одобрить можно только товар на проверке"
