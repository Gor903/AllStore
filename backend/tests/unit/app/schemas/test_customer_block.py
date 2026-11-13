"""A shop's own door: the buyer a seller will not serve.

Asked for by address, because that is how a seller knows the person they fell out with — they
have an order and a conversation, not a uuid.

The shop's name travels only on the staff screens. On the seller's own screen the question is
"who have I barred", and on a moderator's it is "which shops barred this person" — the same
record answers both, and naming the shop on the first would be answering a question nobody
asked while adding one more place for a display name to appear.
"""

import uuid
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.models import Business, BusinessCustomerBlock, BusinessStatus, User
from app.schemas.customer_block import CustomerBlockRead, CustomerBlockRequest


def test_a_buyer_is_barred_by_the_address_the_seller_knows_them_by() -> None:
    request = CustomerBlockRequest(email="buyer@example.am", reason="Не забрал три заказа")

    assert request.email == "buyer@example.am"
    assert request.reason == "Не забрал три заказа"


def test_something_that_is_not_an_address_is_refused() -> None:
    with pytest.raises(ValidationError):
        CustomerBlockRequest(email="buyer at example", reason="Не забрал три заказа")


@pytest.mark.parametrize("reason", ["", "   "])
def test_barring_somebody_without_saying_why_is_refused(reason: str) -> None:
    """The record outlives the quarrel, and a moderator reading it later has only the text."""
    with pytest.raises(ValidationError):
        CustomerBlockRequest(email="buyer@example.am", reason=reason)


def test_the_form_takes_nothing_else() -> None:
    body: dict[str, object] = {
        "email": "buyer@example.am",
        "reason": "Не забрал три заказа",
        "business_id": str(uuid.uuid4()),
    }

    with pytest.raises(ValidationError):
        CustomerBlockRequest(**body)


def _block(**overrides: object) -> BusinessCustomerBlock:
    fields: dict[str, object] = {
        "id": uuid.uuid4(),
        "reason": "Не забрал три заказа",
        "created_at": datetime.now(UTC),
        "revoked_at": None,
    }
    block = BusinessCustomerBlock(**{**fields, **overrides})
    block.buyer = User(id=uuid.uuid4(), email="buyer@example.am")
    block.revoked_by = None
    block.business = Business(
        id=uuid.uuid4(),
        legal_name="ООО Ромашка",
        display_name="Ромашка",
        description=None,
        status=BusinessStatus.ACTIVE,
        created_at=datetime.now(UTC),
    )
    return block


def test_the_sellers_own_screen_is_not_told_the_name_of_its_own_shop() -> None:
    read = CustomerBlockRead.from_block(_block())

    assert read.store_name is None
    assert read.buyer_email == "buyer@example.am"


def test_a_staff_screen_is_told_which_shop_barred_them() -> None:
    """That is the whole question there: one person, and the shops that shut their door."""
    read = CustomerBlockRead.from_block(_block(), with_store=True)

    assert read.store_name == "Ромашка"


def test_a_block_nobody_lifted_is_in_force() -> None:
    read = CustomerBlockRead.from_block(_block())

    assert read.in_force is True
    assert read.revoked_at is None
    assert read.revoked_by_email is None


def test_a_lifted_block_names_whoever_lifted_it() -> None:
    """A seller can bar a buyer and a moderator can undo it; the record says which happened."""
    block = _block(revoked_at=datetime.now(UTC))
    block.revoked_by = User(id=uuid.uuid4(), email="moderator@allstore.am")

    read = CustomerBlockRead.from_block(block)

    assert read.in_force is False
    assert read.revoked_by_email == "moderator@allstore.am"
