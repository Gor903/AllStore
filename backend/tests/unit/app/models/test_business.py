"""A shop, and what is true about it before anybody looks.

One seller owns one business in this version, so the owner is unique. The reason a shop is
where it is lives in the verdict that carries it rather than in a column of its own — two
copies of it would be one too many, and the property is deliberately not named after the
schema field it fills: `reviews` is lazy, and a property the response model reached for by
name would make every answer carrying a business load the history, the catalogue included.
"""

from app.models import Business, BusinessModerationReview, BusinessStatus
from tests.unit.app.models import column_of, default_of, on_delete


def test_the_values_the_status_is_stored_as() -> None:
    assert [status.value for status in BusinessStatus] == [
        "pending",
        "active",
        "rejected",
        "suspended",
        "blocked",
    ]


def test_a_new_shop_waits_to_be_looked_at() -> None:
    assert default_of(Business, "status") is BusinessStatus.PENDING


def test_one_shop_per_seller() -> None:
    assert column_of(Business, "owner_user_id").unique is True


def test_a_shop_goes_with_the_account_that_owns_it() -> None:
    assert on_delete(Business, "owner_user_id") == "CASCADE"


def test_both_names_are_required_because_the_table_says_so() -> None:
    """One is who they are in law and the other is what buyers see; neither path can create a
    business without asking for both."""
    assert column_of(Business, "legal_name").nullable is False
    assert column_of(Business, "display_name").nullable is False


def test_the_reason_is_read_from_the_newest_verdict_that_carries_one() -> None:
    business = Business()
    business.reviews = [
        BusinessModerationReview(reason=None),
        BusinessModerationReview(reason="Нет документов"),
    ]

    assert business.latest_reason == "Нет документов"


def test_a_shop_nobody_said_anything_about_carries_no_reason() -> None:
    business = Business()
    business.reviews = []

    assert business.latest_reason is None


def test_the_property_is_not_named_after_the_field_it_fills() -> None:
    """`status_reason` on the schema is filled by `of`, on purpose: a property with that name
    would be read by `model_validate` and would load the history on every single answer."""
    assert hasattr(Business, "latest_reason")
    assert not hasattr(Business, "status_reason")
