"""A storefront: one shop, one address, and a status that decides whether anybody sees it.

The address is checked by the database as well as by the schema, because it becomes a DNS
label and a certificate name — a row that slipped past the application would be a shop nobody
can reach and a certificate nobody can issue.

A new storefront is a draft: a shop that appeared the moment somebody typed a name would be a
shop nobody had looked at.
"""

from app.models import Store, StoreStatus
from app.models.store import AVAILABLE_THEMES, SUBDOMAIN_MAX_LENGTH
from tests.unit.app.models import check_of, column_of, default_of, length_of, on_delete


def test_the_values_the_status_is_stored_as() -> None:
    assert [status.value for status in StoreStatus] == ["draft", "active", "suspended", "blocked"]


def test_a_new_storefront_is_a_draft() -> None:
    assert default_of(Store, "status") is StoreStatus.DRAFT


def test_one_storefront_per_shop() -> None:
    assert column_of(Store, "business_id").unique is True


def test_a_storefront_belongs_to_its_shop_and_goes_with_it() -> None:
    assert on_delete(Store, "business_id") == "CASCADE"


def test_one_address_per_platform() -> None:
    assert column_of(Store, "subdomain").unique is True


def test_the_database_checks_the_address_too() -> None:
    """It becomes a DNS label: a row that slipped past the application would be a shop nobody
    can reach and a certificate nobody can issue."""
    assert "subdomain ~" in check_of(Store, "ck_stores_subdomain_format")


def test_the_column_is_as_long_as_a_dns_label_may_be() -> None:
    assert length_of(Store, "subdomain") == SUBDOMAIN_MAX_LENGTH


def test_a_shop_that_chose_no_theme_has_the_platform_s() -> None:
    assert default_of(Store, "theme_id") == "default"
    assert "default" in AVAILABLE_THEMES
