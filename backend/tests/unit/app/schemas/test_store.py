"""The address a shop is reached at, and the look a seller may give it.

The subdomain is the part with consequences: it becomes a DNS label and a certificate name, so
what is refused here is refused because the internet would refuse it later and less kindly.

The update form is the other half. Only the fields a body carries change, and `null` means
"back to the default" for the three things that have one — a field not on that list cannot be
cleared, because `null` there would mean a shop with no address or no theme at all.
"""

import uuid
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.models import Business, Store, StoreStatus
from app.models.store import AVAILABLE_THEMES
from app.schemas.store import (
    StoreCreateRequest,
    StorefrontRead,
    StoreRead,
    StoreUpdateRequest,
)


@pytest.mark.parametrize(
    ("typed", "stored"),
    [
        ("cups", "cups"),
        # DNS reads a label case-insensitively: this is the same address, not an error
        ("Cups", "cups"),
        ("  CUPS  ", "cups"),
        ("cups-and-saucers", "cups-and-saucers"),
        ("shop1", "shop1"),
    ],
)
def test_an_address_is_kept_in_the_one_form_dns_will_answer_at(typed: str, stored: str) -> None:
    assert StoreCreateRequest(subdomain=typed).subdomain == stored


@pytest.mark.parametrize(
    "typed",
    [
        "-cups",  # a label may not begin with a hyphen
        "cups-",  # nor end with one
        "cu",  # shorter than three
        "c" * 64,  # longer than a DNS label
        "cups.and.saucers",  # a dot is another level, not a name
        "чашки",  # not an ASCII label
        "cups_shop",  # an underscore is not legal in a hostname
        "",
    ],
)
def test_an_address_the_internet_would_refuse_is_refused_here(typed: str) -> None:
    with pytest.raises(ValidationError):
        StoreCreateRequest(subdomain=typed)


@pytest.mark.parametrize(("typed", "stored"), [("#AABBCC", "#aabbcc"), (" #aAbBcC ", "#aabbcc")])
def test_a_colour_is_kept_in_one_shape(typed: str, stored: str) -> None:
    assert StoreUpdateRequest(primary_color=typed).primary_color == stored


@pytest.mark.parametrize("typed", ["aabbcc", "#abc", "#gggggg", "red", "#aabbccdd"])
def test_something_that_is_not_a_colour_is_refused(typed: str) -> None:
    with pytest.raises(ValidationError):
        StoreUpdateRequest(primary_color=typed)


def test_only_what_the_body_carries_changes() -> None:
    """A form that sent every field would overwrite what another tab had just changed."""
    update = StoreUpdateRequest(description="Чашки ручной работы")

    assert update.model_fields_set == {"description"}


@pytest.mark.parametrize("field", ["description", "primary_color", "secondary_color"])
def test_the_look_can_be_cleared_back_to_the_default(field: str) -> None:
    """Null is how a seller says "none": no description shown, and the theme picks the colour."""
    update = StoreUpdateRequest(**{field: None})

    assert getattr(update, field) is None
    assert field in update.model_fields_set


def test_the_theme_cannot_be_cleared_because_there_is_no_shop_without_one() -> None:
    with pytest.raises(ValidationError, match="нельзя очистить"):
        StoreUpdateRequest(theme_id=None)


def test_a_theme_nobody_wrote_is_refused_with_the_list_of_the_ones_that_exist() -> None:
    """The message carries the available names: a seller who mistyped one can act on that,
    and "unknown theme" alone is something only we could look up."""
    with pytest.raises(ValidationError, match="Неизвестная тема"):
        StoreUpdateRequest(theme_id="neon")


@pytest.mark.parametrize("theme", sorted(AVAILABLE_THEMES))
def test_every_theme_the_platform_ships_is_accepted(theme: str) -> None:
    assert StoreUpdateRequest(theme_id=theme).theme_id == theme


def test_a_field_nobody_declared_is_refused_rather_than_ignored() -> None:
    """`extra="forbid"`: a renamed field in a client would otherwise be silently dropped, and
    the seller would watch their change not happen with nothing to go on."""
    # as a dict, because this is a body a client sent and not a call anybody writes
    body: dict[str, object] = {"subdomain": "cups"}
    with pytest.raises(ValidationError):
        StoreUpdateRequest(**body)


def test_a_description_longer_than_a_shop_has_to_say_is_refused() -> None:
    with pytest.raises(ValidationError):
        StoreUpdateRequest(description="ч" * 2001)


def test_a_description_arrives_without_the_whitespace_around_it() -> None:
    assert StoreUpdateRequest(description="  Чашки  ").description == "Чашки"


def test_what_a_visitor_is_shown_of_a_shop() -> None:
    """Nothing internal is listed — not the legal name, not the identifiers, not the moderation
    status. The way to be sure the public page cannot leak them is to leave them no field."""
    fields = set(StorefrontRead.model_fields)

    assert fields.isdisjoint({"id", "business_id", "legal_name", "status", "created_at"})
    assert "display_name" in fields


def test_what_the_seller_is_shown_of_their_own() -> None:
    """The description lives on the business, so it is passed in rather than read through a
    relation that may not be loaded: a lazy load in the async session has nowhere to run."""
    business_id = uuid.uuid4()
    store = Store(
        id=uuid.uuid4(),
        business_id=business_id,
        subdomain="cups",
        logo_url=None,
        banner_url=None,
        primary_color=None,
        secondary_color=None,
        theme_id="default",
        status=StoreStatus.ACTIVE,
        created_at=datetime.now(UTC),
    )
    business = Business(id=business_id, description="Чашки ручной работы")

    read = StoreRead.of(store, business)

    assert read.description == "Чашки ручной работы"
    assert read.subdomain == "cups"
