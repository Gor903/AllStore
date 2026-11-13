"""The reference book: two levels, an address, and a way to hide one without losing its goods.

The slug is checked by the database as well as by the schema, because it is what a visitor has
in a filter link and what somebody may have saved.

A hidden category is the alternative to deleting one — deletion is refused at the product's
end (RESTRICT there), so this status is what the administrator actually uses.
"""

from app.models import Category, CategoryStatus
from app.models.category import CATEGORY_SLUG_MAX_LENGTH
from tests.unit.app.models import check_of, column_of, default_of, length_of, on_delete


def test_the_values_the_status_is_stored_as() -> None:
    assert [status.value for status in CategoryStatus] == ["active", "hidden"]


def test_a_new_category_is_visible() -> None:
    assert default_of(Category, "status") is CategoryStatus.ACTIVE


def test_one_address_per_category() -> None:
    assert column_of(Category, "slug").unique is True
    assert length_of(Category, "slug") == CATEGORY_SLUG_MAX_LENGTH


def test_the_database_checks_the_address_too() -> None:
    assert "slug ~" in check_of(Category, "ck_categories_slug_format")


def test_a_section_taken_away_takes_its_subsections_with_it() -> None:
    """The products are protected at their own end; the tree is not a thing to half-delete."""
    assert on_delete(Category, "parent_id") == "CASCADE"


def test_a_top_level_category_has_no_parent() -> None:
    assert column_of(Category, "parent_id").nullable is True
