"""The status machine of a product, and the only place its statuses are moved.

    moderation:   pending ──approve──> approved ──edit/submit──> pending
                  pending ──reject───> rejected ──submit───────> pending

    publication:  draft ──approve──> published ──hide──> hidden ──publish──> published
                  reject / submit ──> draft

Publication never runs ahead of moderation: nothing reaches `published` except through
`approve` or a `publish` of an already approved product.
"""

from app.core.errors import ConflictError
from app.models import ModerationStatus, Product, PublicationStatus


class InvalidTransitionError(ConflictError):
    code = "invalid_transition"


def approve(product: Product) -> None:
    """An approved product goes on the shelf at once — there is nothing left to wait for."""
    _require(
        product.moderation_status is ModerationStatus.PENDING,
        "Одобрить можно только товар на проверке",
    )
    product.moderation_status = ModerationStatus.APPROVED
    product.publication_status = PublicationStatus.PUBLISHED


def reject(product: Product) -> None:
    _require(
        product.moderation_status is ModerationStatus.PENDING,
        "Отклонить можно только товар на проверке",
    )
    product.moderation_status = ModerationStatus.REJECTED
    product.publication_status = PublicationStatus.DRAFT


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


def submit_for_review(product: Product) -> None:
    """The seller puts the product back in the queue — after a refusal, or after editing
    what a moderator had already approved."""
    _require(product.moderation_status is not ModerationStatus.PENDING, "Товар уже на проверке")
    product.moderation_status = ModerationStatus.PENDING
    product.publication_status = PublicationStatus.DRAFT


def withdraw(product: Product) -> None:
    """Archiving takes the product off the shelf. It is the seller's own doing, not a verdict,
    so the moderation status keeps whatever it said."""
    product.publication_status = PublicationStatus.HIDDEN


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise InvalidTransitionError(message)
