"""The shop window: everything a visitor who is nobody in particular may see.

Nothing internal is listed in this module — no identifiers of a business, no moderation or
publication status, no stock figures, no legal name. The way to be sure none of them can leak
onto a public page is for these shapes to have no field to carry one, so that is what is
asserted: not only what is shown but what is absent.

Contacts are the one thing a seller publishes on purpose, and they ride along on the product
page and not in a listing — twenty cards from one shop would repeat the same phone twenty
times, and a buyer scrolling a catalogue has not asked anybody for a telephone number yet.
"""

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from app.models import (
    Business,
    BusinessStatus,
    Category,
    ContactPlatform,
    ModerationStatus,
    Product,
    ProductAvailability,
    PublicationStatus,
    Store,
    StoreStatus,
)
from app.models.contact import SocialLink
from app.schemas.catalog import (
    CatalogProductDetailRead,
    CatalogProductListResponse,
    CatalogProductRead,
    CatalogStoreRead,
    CategoryTreeRead,
)

INTERNAL = {
    "business_id",
    "legal_name",
    "moderation_status",
    "publication_status",
    "stock_quantity",
    "rejection_reason",
    "pending_change",
}


def _product() -> Product:
    business = Business(
        id=uuid.uuid4(),
        legal_name="ООО Ромашка",
        display_name="Ромашка",
        description="Чашки ручной работы",
        status=BusinessStatus.ACTIVE,
        created_at=datetime.now(UTC),
    )
    business.store = Store(
        id=uuid.uuid4(),
        business_id=business.id,
        subdomain="cups",
        logo_url=None,
        banner_url=None,
        theme_id="default",
        status=StoreStatus.ACTIVE,
        created_at=datetime.now(UTC),
    )
    business.social_links = [
        SocialLink(
            id=uuid.uuid4(),
            business_id=business.id,
            platform=ContactPlatform.PHONE,
            value="+37410123456",
        )
    ]
    product = Product(
        id=uuid.uuid4(),
        business_id=business.id,
        category_id=uuid.uuid4(),
        name="Чашка",
        description=None,
        price=Decimal("1500.00"),
        currency="AMD",
        stock_quantity=7,
        availability_status=ProductAvailability.IN_STOCK,
        moderation_status=ModerationStatus.APPROVED,
        publication_status=PublicationStatus.PUBLISHED,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    product.business = business
    product.category = Category(id=product.category_id, slug="dishes", name="Посуда")
    product.images = []
    return product


def test_a_card_names_the_shop_a_visitor_can_walk_into() -> None:
    card = CatalogProductRead.from_product(_product())

    assert card.store.subdomain == "cups"
    assert card.store.display_name == "Ромашка"
    assert card.category.slug == "dishes"


def test_a_card_carries_nothing_a_visitor_has_no_business_knowing() -> None:
    fields = set(CatalogProductRead.model_fields)

    assert fields.isdisjoint(INTERNAL), fields & INTERNAL


def test_the_shop_a_card_names_carries_no_internal_fields_either() -> None:
    """The nesting is where a leak hides: the card is clean and the thing inside it is not."""
    card = CatalogProductRead.from_product(_product())

    assert set(type(card.store).model_fields) == {"subdomain", "display_name"}


def test_a_listing_does_not_repeat_the_sellers_telephone_on_every_card() -> None:
    card = CatalogProductRead.from_product(_product())

    assert "contacts" not in type(card.store).model_fields


def test_the_product_page_is_where_the_ways_to_reach_the_seller_live() -> None:
    """That is the page where somebody has decided they want this thing and now needs to ask
    about it — and the contacts are what the seller published for exactly that moment."""
    page = CatalogProductDetailRead.from_product(_product())

    assert [contact.value for contact in page.store.contacts] == ["+37410123456"]


def test_the_page_is_the_card_plus_the_contacts_and_nothing_else() -> None:
    assert set(CatalogProductDetailRead.model_fields) == set(CatalogProductRead.model_fields)


def test_a_shop_in_the_listing_of_shops_shows_what_it_says_about_itself() -> None:
    store = _product().business.store
    assert store is not None

    read = CatalogStoreRead.from_store(store)

    assert read.display_name == "Ромашка"
    assert read.description == "Чашки ручной работы"
    assert [contact.platform for contact in read.contacts] == [ContactPlatform.PHONE]
    assert set(CatalogStoreRead.model_fields).isdisjoint(INTERNAL)


def test_which_results_were_found_by_meaning_is_a_property_of_the_search() -> None:
    """Not of the product. On the card it would follow a product onto its own page, where
    there is no query for it to be relative to and the flag would mean nothing."""
    assert "by_meaning" in CatalogProductListResponse.model_fields
    assert "by_meaning" not in CatalogProductRead.model_fields


def test_a_search_that_found_nothing_by_meaning_says_so_with_an_empty_list() -> None:
    answer = CatalogProductListResponse(items=[], total=0, limit=24, offset=0)

    assert answer.by_meaning == []


def test_the_reference_book_is_two_levels_deep() -> None:
    """Two is what the repository loads; a third would lazy load inside the async session,
    which has nowhere to run."""
    root = Category(id=uuid.uuid4(), slug="dishes", name="Посуда")
    root.children = [Category(id=uuid.uuid4(), slug="cups", name="Чашки")]

    tree = CategoryTreeRead.from_root(root)

    assert [child.slug for child in tree.children] == ["cups"]
    assert tree.children[0].children == []


def test_a_category_with_nothing_under_it_is_a_leaf_rather_than_a_failure() -> None:
    leaf = CategoryTreeRead.leaf(Category(id=uuid.uuid4(), slug="cups", name="Чашки"))

    assert leaf.children == []
