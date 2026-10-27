"""The status machine of a product, and the only place its statuses are moved.

What the public sees lives on the product. What has been proposed lives on a revision, and
a verdict is passed on the revision rather than on the product:

    revision:     pending ──approve──> approved      (its text becomes the product's)
                  pending ──reject───> rejected      (the product is left exactly as it was)
                  pending ──a newer proposal──> superseded

    moderation:   pending ──first approval──> approved ─────────────────────> approved
                  pending ──first refusal───> rejected ──new proposal──> pending

    publication:  draft ──first approval──> published ──hide──> hidden ──publish──> published

That split is the point of the whole stage. Before it, editing an approved product sent it
back to `pending` and took it off the shelf, so fixing a typo cost the seller their listing
for as long as the queue was busy. Now the shelf keeps the last approved version until a
moderator says otherwise, and a refusal of a change costs nothing that was already earned.

Publication never runs ahead of moderation: nothing reaches `published` except through the
approval of a revision, or a `publish` of an already approved product.
"""

from datetime import UTC, datetime

from app.core.errors import ConflictError
from app.models import (
    ModerationStatus,
    Product,
    ProductRevision,
    PublicationStatus,
    RevisionStatus,
)


class InvalidTransitionError(ConflictError):
    code = "invalid_transition"


def approve_revision(product: Product, revision: ProductRevision) -> None:
    """The proposal becomes what the buyer sees."""
    _require(revision.is_pending, "Одобрить можно только изменение на проверке")
    _close(revision, RevisionStatus.APPROVED)

    product.name = revision.name
    product.description = revision.description
    product.category_id = revision.category_id
    product.moderation_status = ModerationStatus.APPROVED
    if product.publication_status is PublicationStatus.DRAFT:
        # the first approval is what puts a product on the shelf; a hidden one stays hidden,
        # because a moderator took it down and an edit is not an appeal against that
        product.publication_status = PublicationStatus.PUBLISHED


def reject_revision(product: Product, revision: ProductRevision, reason: str) -> None:
    """The proposal is refused. What happens to the product depends on whether it had
    anything to lose: a product that was never approved goes to `rejected`, and one already
    on the shelf stays there, under the text that was approved before."""
    _require(revision.is_pending, "Отклонить можно только изменение на проверке")
    _close(revision, RevisionStatus.REJECTED, reason)

    if product.moderation_status is not ModerationStatus.APPROVED:
        product.moderation_status = ModerationStatus.REJECTED
        product.publication_status = PublicationStatus.DRAFT


def supersede(revision: ProductRevision) -> None:
    """A newer proposal arrived before anybody judged this one."""
    _close(revision, RevisionStatus.SUPERSEDED)


def hide(product: Product) -> None:
    _require(
        product.publication_status is PublicationStatus.PUBLISHED,
        "Скрыть можно только опубликованный товар",
    )
    product.publication_status = PublicationStatus.HIDDEN


def publish(product: Product) -> None:
    """Puts a hidden product back on the shelf. An unapproved one never gets there."""
    _require(
        product.moderation_status is ModerationStatus.APPROVED,
        "Опубликовать можно только одобренный товар",
    )
    _require(
        product.publication_status is PublicationStatus.HIDDEN,
        "Товар не скрыт, публиковать нечего",
    )
    product.publication_status = PublicationStatus.PUBLISHED


def withdraw(product: Product) -> None:
    """Archiving takes the product off the shelf. It is the seller's own doing, not a verdict,
    so the moderation status keeps whatever it said."""
    product.publication_status = PublicationStatus.HIDDEN


def _close(revision: ProductRevision, status: RevisionStatus, reason: str | None = None) -> None:
    revision.status = status
    revision.reason = reason
    revision.decided_at = datetime.now(UTC)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise InvalidTransitionError(message)
