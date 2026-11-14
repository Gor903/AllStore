"""A shop's own door: the buyer one seller will not serve.

The same shape as an account ban and a different reach: it binds a buyer to one business, and
the buyer keeps their account, keeps every other shop, and keeps the ability to complain about
this one. Which is why the business is RESTRICT as well as the buyer — a shop that deleted
itself would otherwise take the record of its own refusals with it.
"""

from datetime import UTC, datetime

from app.models import BusinessCustomerBlock
from tests.unit.app.models import check_of, table_of, where_of


def _on_delete(column: str) -> str | None:
    key = next(k for k in table_of(BusinessCustomerBlock).foreign_keys if k.parent.name == column)
    return key.ondelete


def test_the_record_outlives_both_sides_of_the_quarrel() -> None:
    assert _on_delete("buyer_user_id") == "RESTRICT"
    assert _on_delete("business_id") == "RESTRICT"


def test_it_outlives_whoever_decided_it() -> None:
    assert _on_delete("created_by_user_id") == "SET NULL"
    assert _on_delete("revoked_by_user_id") == "SET NULL"


def test_one_closed_door_per_buyer_per_shop() -> None:
    index = next(
        i
        for i in table_of(BusinessCustomerBlock).indexes
        if i.name == "uq_business_customer_blocks_in_force"
    )

    assert index.unique is True
    assert "revoked_at IS NULL" in where_of(index)


def test_a_reason_of_whitespace_is_not_a_reason() -> None:
    assert r"\S" in check_of(BusinessCustomerBlock, "ck_business_customer_blocks_reason")


def test_a_block_nobody_lifted_is_the_one_in_force() -> None:
    block = BusinessCustomerBlock(revoked_at=None)
    assert block.in_force is True

    block.revoked_at = datetime.now(UTC)
    assert block.in_force is False
