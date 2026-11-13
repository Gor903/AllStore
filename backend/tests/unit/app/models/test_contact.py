"""The ways a seller publishes to be reached.

The platform's order is the enum's order, so every storefront lists them the same way — a shop
whose telephone moved below its facebook because of the order rows were inserted in would look
different for no reason anybody chose.

The value is checked for being something rather than nothing by the database as well: a blank
contact is a link a buyer taps and nothing happens.
"""

from app.models import ContactPlatform
from app.models.contact import SocialLink
from tests.unit.app.models import check_of, on_delete, table_of


def test_the_values_each_platform_is_stored_as() -> None:
    assert [platform.value for platform in ContactPlatform] == [
        "phone",
        "whatsapp",
        "telegram",
        "viber",
        "instagram",
        "facebook",
    ]


def test_the_telephone_comes_first_because_that_is_how_people_are_reached_here() -> None:
    assert next(iter(ContactPlatform)) is ContactPlatform.PHONE


def test_contacts_are_listed_in_the_platform_s_own_order() -> None:
    """Ordered by the enum on the relationship, not by when a row happened to be written."""
    from app.models import Business

    order = str(Business.social_links.property.order_by[0])
    assert "platform" in order


def test_a_blank_contact_is_refused_by_the_database() -> None:
    assert r"\S" in check_of(SocialLink, "ck_social_links_value_not_blank")


def test_contacts_belong_to_the_shop_and_go_with_it() -> None:
    assert on_delete(SocialLink, "business_id") == "CASCADE"


def test_the_address_is_not_stored() -> None:
    """It is built on read, so no row in this table can send a buyer somewhere we did not
    mean to send them."""
    assert "href" not in table_of(SocialLink).columns
    assert "url" not in table_of(SocialLink).columns
