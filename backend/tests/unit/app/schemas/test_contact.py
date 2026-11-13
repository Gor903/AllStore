"""What a seller typed into the contacts form, and what came out of it.

Sellers paste what their application gave them: the full link to a profile as often as the
handle, and a number with spaces and brackets as often as one in international form. The
schema brings all of that to one shape before the database, because otherwise a buyer is shown
a link that leads nowhere.

The address is not stored. It is built on read, so no string in the database can send a buyer
somewhere we did not mean to send them.
"""

import pytest
from pydantic import ValidationError

from app.models import ContactPlatform
from app.schemas.contact import ContactsRequest, ContactWrite, href_of


def _written(platform: ContactPlatform, value: str) -> str:
    return ContactWrite(platform=platform, value=value).value


@pytest.mark.parametrize(
    ("typed", "stored"),
    [
        ("+37410123456", "+37410123456"),
        ("+374 10 123 456", "+37410123456"),
        ("+374 (10) 123-456", "+37410123456"),
        # how it is dialled from a landline: the international prefix instead of a plus
        ("0037410123456", "+37410123456"),
    ],
)
def test_a_number_is_stored_the_one_way_it_can_be_dialled(typed: str, stored: str) -> None:
    assert _written(ContactPlatform.PHONE, typed) == stored


@pytest.mark.parametrize(
    "typed",
    [
        "10123456",  # no country
        "+0374101234",  # a country code starting at zero
        "+374",  # too short
        "+3741012345678901234",  # longer than fifteen digits
        "не телефон",
    ],
)
def test_a_number_that_cannot_be_dialled_is_refused(typed: str) -> None:
    with pytest.raises(ValidationError, match="международном формате"):
        _written(ContactPlatform.PHONE, typed)


@pytest.mark.parametrize(
    ("platform", "typed"),
    [
        (ContactPlatform.TELEGRAM, "https://t.me/seller_shop"),
        (ContactPlatform.TELEGRAM, "http://telegram.me/seller_shop"),
        (ContactPlatform.TELEGRAM, "t.me/seller_shop"),
        (ContactPlatform.TELEGRAM, "www.t.me/seller_shop/"),
        (ContactPlatform.TELEGRAM, "@seller_shop"),
        (ContactPlatform.TELEGRAM, "seller_shop"),
        # the tail an application appends to a link to a profile
        (ContactPlatform.TELEGRAM, "https://t.me/seller_shop?start=1"),
    ],
)
def test_a_pasted_link_becomes_the_handle_inside_it(platform: ContactPlatform, typed: str) -> None:
    assert _written(platform, typed) == "seller_shop"


def test_each_platform_keeps_its_own_idea_of_a_handle() -> None:
    """A dot is legal on instagram and facebook and illegal on telegram; so are the lengths."""
    assert _written(ContactPlatform.INSTAGRAM, "instagram.com/sell.er") == "sell.er"
    assert _written(ContactPlatform.FACEBOOK, "fb.com/seller.shop") == "seller.shop"

    with pytest.raises(ValidationError, match="имя профиля"):
        _written(ContactPlatform.TELEGRAM, "sell.er")
    with pytest.raises(ValidationError, match="имя профиля"):
        # telegram wants five characters
        _written(ContactPlatform.TELEGRAM, "shop")


def test_one_contact_per_platform() -> None:
    """The settings screen is one form and the whole set is replaced at once. Two phone
    numbers would mean the buyer is shown one and the seller was editing the other."""
    with pytest.raises(ValidationError, match="только один раз"):
        ContactsRequest(
            items=[
                {"platform": ContactPlatform.PHONE, "value": "+37410123456"},
                {"platform": ContactPlatform.PHONE, "value": "+37410123457"},
            ]
        )


def test_an_empty_set_is_a_valid_answer() -> None:
    """A seller who removed every contact is an empty list, not a form that refuses them."""
    assert ContactsRequest().items == []


@pytest.mark.parametrize(
    ("platform", "value", "href"),
    [
        (ContactPlatform.PHONE, "+37410123456", "tel:+37410123456"),
        # wa.me takes the number without the plus
        (ContactPlatform.WHATSAPP, "+37410123456", "https://wa.me/37410123456"),
        (ContactPlatform.VIBER, "+37410123456", "viber://chat?number=%2B37410123456"),
        (ContactPlatform.TELEGRAM, "seller_shop", "https://t.me/seller_shop"),
        (ContactPlatform.INSTAGRAM, "sell.er", "https://instagram.com/sell.er"),
        (ContactPlatform.FACEBOOK, "seller.shop", "https://facebook.com/seller.shop"),
    ],
)
def test_the_address_is_built_per_platform(
    platform: ContactPlatform, value: str, href: str
) -> None:
    assert href_of(platform, value) == href
