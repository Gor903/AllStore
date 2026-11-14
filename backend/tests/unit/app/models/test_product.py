"""A product, and the three things that are true about it at once.

A moderator's verdict, where it stands on the shelf, and whether an edit is waiting to be
judged are separate columns and a separate history on purpose. The properties here are what
turn them into one sentence for the seller, and each of them reads the loaded history rather
than a column of its own — the reason lives in the verdict that carries it, and two copies of
it would be one too many.

The two refusals are different things. `rejection_reason` is about a product that never made
it onto the shelf; `change_rejection_reason` is about a listing that is still live and whose
edit was turned down — a case the seller has no other way of being told about.

The table's own decisions: a category is RESTRICT, because removing one must not silently take
its products with it; the business is CASCADE, because a shop's products are the shop's.
"""

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import Numeric

from app.models import (
    ModerationDecision,
    ModerationReview,
    ModerationStatus,
    Product,
    ProductAvailability,
    ProductImage,
    PublicationStatus,
)
from app.models.product_revision import ProductRevision, RevisionStatus
from tests.unit.app.models import check_of, column_of, default_of, on_delete, table_of


def _on_delete(column: str) -> str | None:
    key = next(k for k in table_of(Product).foreign_keys if k.parent.name == column)
    return key.ondelete


def _product(status: ModerationStatus = ModerationStatus.APPROVED) -> Product:
    product = Product(moderation_status=status, price=Decimal("1500.00"))
    product.reviews = []
    product.revisions = []
    return product


def _revision(status: RevisionStatus, reason: str | None = None) -> ProductRevision:
    return ProductRevision(status=status, reason=reason, created_at=datetime.now(UTC))


def test_the_values_each_state_is_stored_as() -> None:
    assert [value.value for value in ProductAvailability] == ["in_stock", "out_of_stock"]
    assert [value.value for value in ModerationStatus] == ["pending", "approved", "rejected"]
    assert [value.value for value in PublicationStatus] == ["draft", "published", "hidden"]


def test_a_new_product_is_invisible_until_somebody_looks_at_it() -> None:
    assert default_of(Product, "moderation_status") is ModerationStatus.PENDING
    assert default_of(Product, "publication_status") is PublicationStatus.DRAFT


def test_removing_a_category_must_not_take_its_products_with_it() -> None:
    assert _on_delete("category_id") == "RESTRICT"


def test_a_shops_products_belong_to_the_shop() -> None:
    assert _on_delete("business_id") == "CASCADE"


def test_the_database_refuses_a_negative_price_or_stock() -> None:
    """The schema refuses them too; this is the floor under a path that never went through it."""
    assert "price >= 0" in check_of(Product, "ck_products_price_non_negative")
    assert "stock_quantity >= 0" in check_of(Product, "ck_products_stock_non_negative")


def test_a_price_is_kept_as_a_decimal_with_the_scale_money_has() -> None:
    price = column_of(Product, "price").type
    assert isinstance(price, Numeric)

    assert price.scale == 2


def test_a_product_with_nothing_proposed_has_no_pending_change() -> None:
    assert _product().pending_revision is None


def test_the_one_waiting_proposal_is_the_pending_one() -> None:
    """At most one exists — a unique partial index says so — which is what lets a moderator
    act on "the product" without being asked which proposal."""
    product = _product()
    pending = _revision(RevisionStatus.PENDING)
    product.revisions = [pending, _revision(RevisionStatus.APPROVED)]

    assert product.pending_revision is pending


def test_a_refused_edit_is_told_to_the_seller_while_the_listing_stands() -> None:
    product = _product()
    product.revisions = [_revision(RevisionStatus.REJECTED, "Фото не то")]

    assert product.change_rejection_reason == "Фото не то"


def test_an_approved_edit_leaves_nothing_to_say() -> None:
    """Only the newest judged proposal counts: an older refusal has been answered."""
    product = _product()
    product.revisions = [
        _revision(RevisionStatus.APPROVED),
        _revision(RevisionStatus.REJECTED, "Фото не то"),
    ]

    assert product.change_rejection_reason is None


def test_a_proposal_still_waiting_is_not_a_refusal() -> None:
    product = _product()
    product.revisions = [_revision(RevisionStatus.PENDING)]

    assert product.change_rejection_reason is None


def test_a_product_that_was_never_refused_carries_no_reason() -> None:
    product = _product(ModerationStatus.APPROVED)
    product.reviews = [
        ModerationReview(decision=ModerationDecision.REJECTED, reason="Старое решение")
    ]

    assert product.rejection_reason is None


def test_a_refused_product_carries_what_to_act_on() -> None:
    product = _product(ModerationStatus.REJECTED)
    product.reviews = [ModerationReview(decision=ModerationDecision.REJECTED, reason="Нет фото")]

    assert product.rejection_reason == "Нет фото"


def test_a_refused_product_with_no_verdict_loaded_says_nothing_rather_than_breaking() -> None:
    """The history is a lazy relationship and the caller decides whether to load it."""
    assert _product(ModerationStatus.REJECTED).rejection_reason is None


def test_a_photograph_belongs_to_its_product_and_goes_with_it() -> None:
    assert on_delete(ProductImage, "product_id") == "CASCADE"


def test_a_gallery_has_an_order_and_it_starts_at_zero() -> None:
    """The lowest one is the cover, so a negative position would be a cover nobody chose."""
    checks = {
        c.name: str(c.sqltext) for c in table_of(ProductImage).constraints if hasattr(c, "sqltext")
    }

    assert "sort_order >= 0" in checks["ck_product_images_sort_order_non_negative"]
    assert default_of(ProductImage, "sort_order") == 0
