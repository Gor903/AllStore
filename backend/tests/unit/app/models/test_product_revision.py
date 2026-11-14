"""A proposed change to a product, waiting to be judged.

Only the moderated fields are here. Price and stock change under the seller's own hand and
always did — a moderator did not approve the price, and holding it hostage to a queue would
make the shelf wrong rather than careful.

One proposal in the queue per product, by a partial unique index: a second edit replaces the
first rather than queueing beside it, so a moderator never has to guess which one is current.
"""

from app.models.product_revision import ProductRevision, RevisionStatus
from tests.unit.app.models import check_of, default_of, index_of, table_of, where_of


def _on_delete(column: str) -> str | None:
    return next(
        k for k in table_of(ProductRevision).foreign_keys if k.parent.name == column
    ).ondelete


def test_the_values_the_status_is_stored_as() -> None:
    assert [status.value for status in RevisionStatus] == [
        "pending",
        "approved",
        "rejected",
        "superseded",
    ]


def test_a_new_proposal_waits() -> None:
    assert default_of(ProductRevision, "status") is RevisionStatus.PENDING


def test_only_the_moderated_fields_are_proposed() -> None:
    """Price and stock are not here: they are the seller's own, and queueing them would make
    the shelf wrong rather than careful."""
    columns = set(table_of(ProductRevision).columns.keys())

    assert {"name", "description", "category_id"} <= columns
    assert columns.isdisjoint({"price", "stock_quantity", "currency"})


def test_one_proposal_in_the_queue_per_product() -> None:
    index = index_of(ProductRevision, "uq_product_revisions_pending")

    assert index.unique is True
    assert "status = 'pending'" in where_of(index)


def test_refusing_a_proposal_without_a_reason_is_refused() -> None:
    clause = check_of(ProductRevision, "ck_product_revisions_reason_for_rejection")

    assert "rejected" in clause
    assert r"\S" in clause


def test_a_proposal_belongs_to_its_product() -> None:
    assert _on_delete("product_id") == "CASCADE"


def test_a_proposed_category_cannot_be_deleted_out_from_under_it() -> None:
    assert _on_delete("category_id") == "RESTRICT"


def test_the_moderator_who_judged_it_may_go_and_the_verdict_stays() -> None:
    assert _on_delete("moderator_id") == "SET NULL"


def test_only_a_pending_proposal_is_pending() -> None:
    assert ProductRevision(status=RevisionStatus.PENDING).is_pending is True
    assert ProductRevision(status=RevisionStatus.APPROVED).is_pending is False
    assert ProductRevision(status=RevisionStatus.SUPERSEDED).is_pending is False
