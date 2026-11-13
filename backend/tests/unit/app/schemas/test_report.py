"""A complaint: exactly one subject, said in words.

"Something is wrong somewhere" is not a complaint anybody can act on, so the form insists on a
product or a shop and refuses both at once as firmly as it refuses neither.

A shop is named by its subdomain rather than by an identifier, because that is what a visitor
has in front of them — the public storefront deliberately carries no internal ids.

What comes back to the person who complained is one identifier and nothing else. They have no
business knowing what became of it or how many others filed one.
"""

import uuid
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.models import Business, BusinessStatus, Store, StoreStatus
from app.models.report import REASON_MAX_LENGTH
from app.repositories.reports import OpenSubject
from app.schemas.report import ReportAccepted, ReportedSubjectRead, ReportRequest

PRODUCT = uuid.uuid4()


def test_a_complaint_about_a_product_names_the_product() -> None:
    report = ReportRequest(product_id=PRODUCT, reason="Фото чужое")

    assert report.product_id == PRODUCT
    assert report.subdomain is None


def test_a_complaint_about_a_shop_names_the_address_the_visitor_sees() -> None:
    report = ReportRequest(subdomain="Cups", reason="Берут деньги мимо площадки")

    # the same normalisation as everywhere a subdomain is read: DNS does not care about case
    assert report.subdomain == "cups"


def test_a_complaint_about_nothing_is_refused() -> None:
    with pytest.raises(ValidationError, match="либо товар, либо магазин"):
        ReportRequest(reason="Что-то не так")


def test_a_complaint_about_both_at_once_is_refused() -> None:
    """A moderator closing it would have to decide which of the two the verdict applied to,
    and whichever they chose, the other half would stay open with nobody looking at it."""
    with pytest.raises(ValidationError, match="либо товар, либо магазин"):
        ReportRequest(product_id=PRODUCT, subdomain="cups", reason="Что-то не так")


@pytest.mark.parametrize("reason", ["", "   ", "ч" * (REASON_MAX_LENGTH + 1)])
def test_a_complaint_with_nothing_readable_in_it_is_refused(reason: str) -> None:
    with pytest.raises(ValidationError):
        ReportRequest(product_id=PRODUCT, reason=reason)


def test_a_reason_arrives_trimmed() -> None:
    assert ReportRequest(product_id=PRODUCT, reason="  Фото чужое  ").reason == "Фото чужое"


def test_the_complainant_is_told_nothing_but_that_it_was_taken() -> None:
    """No status, no count, no verdict: a complaint is not a conversation, and anything more
    here would tell one person what another person's shop is accused of."""
    assert set(ReportAccepted.model_fields) == {"id"}


def _subject(**overrides: object) -> OpenSubject:
    fields: dict[str, object] = {
        "product_id": None,
        "business_id": None,
        "total": 3,
        "last_at": datetime.now(UTC),
        "reasons": ["Фото чужое", "Фото чужое", "Цена не та"],
    }
    return OpenSubject(**{**fields, **overrides})  # type: ignore[arg-type]


def _business(*, with_store: bool) -> Business:
    business = Business(
        id=uuid.uuid4(),
        legal_name="ООО Ромашка",
        display_name="Ромашка",
        description=None,
        status=BusinessStatus.ACTIVE,
        created_at=datetime.now(UTC),
    )
    business.store = (
        Store(
            id=uuid.uuid4(),
            business_id=business.id,
            subdomain="cups",
            theme_id="default",
            status=StoreStatus.ACTIVE,
            created_at=datetime.now(UTC),
        )
        if with_store
        else None
    )
    return business


def test_one_line_of_the_queue_carries_every_reason_that_was_given() -> None:
    """Twenty complaints about one product are one piece of work and twenty things said; the
    count tells a moderator how urgent it is and the texts tell them what it is about."""
    business = _business(with_store=True)

    line = ReportedSubjectRead.of(_subject(business_id=business.id), {}, {business.id: business})

    assert line.total == 3
    assert line.reasons == ["Фото чужое", "Фото чужое", "Цена не та"]
    assert line.shop is not None
    assert line.shop.display_name == "Ромашка"
    assert line.shop.subdomain == "cups"


def test_a_complained_about_shop_with_no_storefront_is_still_shown() -> None:
    business = _business(with_store=False)

    line = ReportedSubjectRead.of(_subject(business_id=business.id), {}, {business.id: business})

    assert line.shop is not None
    assert line.shop.subdomain is None


def test_a_subject_that_has_since_disappeared_leaves_the_line_readable() -> None:
    """A product deleted between the query and the read is an ordinary race, and a queue that
    threw on it would be a queue a moderator cannot open."""
    line = ReportedSubjectRead.of(_subject(product_id=PRODUCT), {}, {})

    assert line.product is None
    assert line.shop is None
    assert line.total == 3
