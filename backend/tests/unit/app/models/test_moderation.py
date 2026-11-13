"""Verdicts: what was decided, by whom, and why — when why is required.

A refusal without a reason is one the seller cannot act on, so the database refuses to store
one. `\\S` means at least one character that is not whitespace, which is what keeps a line of
spaces from passing for an explanation.

A moderator's account may go; what they decided may not. Hence SET NULL on the actor and
CASCADE on the subject — a verdict about a product that no longer exists is about nothing.
"""

from app.models import (
    BusinessDecision,
    BusinessModerationReview,
    ModerationDecision,
    ModerationReview,
)
from tests.unit.app.models import check_of, column_of, on_delete


def test_the_values_a_product_verdict_is_stored_as() -> None:
    assert [decision.value for decision in ModerationDecision] == [
        "approved",
        "rejected",
        "hidden",
        "published",
    ]


def test_the_values_a_shop_verdict_is_stored_as() -> None:
    assert [decision.value for decision in BusinessDecision] == [
        "approved",
        "rejected",
        "suspended",
        "blocked",
        "restored",
        "resubmitted",
    ]


def test_refusing_a_product_without_a_reason_is_refused_by_the_database() -> None:
    clause = check_of(ModerationReview, "ck_moderation_reviews_reason_for_rejection")

    assert "rejected" in clause
    assert r"\S" in clause


def test_so_is_taking_a_seller_off_the_air_without_one() -> None:
    """All three of the ways to do it: refused, suspended, blocked."""
    clause = check_of(
        BusinessModerationReview,
        "ck_business_moderation_reviews_reason_for_refusal",
    )

    for decision in ("rejected", "suspended", "blocked"):
        assert decision in clause
    assert r"\S" in clause


def test_an_approval_needs_no_explanation() -> None:
    """The clause only binds the refusals, which is why it reads as an implication."""
    clause = check_of(ModerationReview, "ck_moderation_reviews_reason_for_rejection")

    assert "OR" in clause.upper()


def test_a_verdict_outlives_the_moderator_who_passed_it() -> None:
    assert on_delete(ModerationReview, "moderator_id") == "SET NULL"
    assert on_delete(BusinessModerationReview, "moderator_id") == "SET NULL"


def test_a_verdict_about_nothing_is_nothing() -> None:
    assert on_delete(ModerationReview, "product_id") == "CASCADE"
    assert on_delete(BusinessModerationReview, "business_id") == "CASCADE"


def test_a_verdict_may_be_about_the_product_as_a_whole() -> None:
    """Verdicts that predate revisions were, and hide or publish still are."""
    assert column_of(ModerationReview, "revision_id").nullable is True
    assert on_delete(ModerationReview, "revision_id") == "SET NULL"
