"""A complaint about a product or a shop.

Every complaint is its own row even when twenty people report the same thing: each is a
separate fact, and twenty of them say something one does not. The queue groups them by
subject, so the repetition informs rather than floods.

A guest may complain — somebody who has just been cheated is not going to register first — so
the reporter is nullable. Exactly one subject, enforced by the database: a complaint about
"something" is not one anybody can act on, and a complaint about both would be a verdict
nobody could address.
"""

from app.models import Report, ReportStatus
from app.models.report import ONE_SUBJECT
from tests.unit.app.models import check_of, column_of, default_of, table_of


def _on_delete(column: str) -> str | None:
    return next(k for k in table_of(Report).foreign_keys if k.parent.name == column).ondelete


def test_the_values_the_status_is_stored_as() -> None:
    assert [status.value for status in ReportStatus] == ["open", "upheld", "dismissed"]


def test_a_new_complaint_is_open() -> None:
    assert default_of(Report, "status") is ReportStatus.OPEN


def test_exactly_one_subject_and_the_database_says_so() -> None:
    """Not neither, and not both: `<>` between two IS NULL tests is the shortest way to say
    "exactly one of these", and it is the same rule the schema applies to the form."""
    assert ONE_SUBJECT == "(product_id IS NULL) <> (business_id IS NULL)"
    assert ONE_SUBJECT in check_of(Report, "ck_reports_one_subject")


def test_dismissing_a_complaint_without_saying_why_is_refused() -> None:
    clause = check_of(Report, "ck_reports_reason_for_dismissal")

    assert "dismissed" in clause
    assert r"\S" in clause


def test_a_guest_may_complain() -> None:
    assert column_of(Report, "reporter_user_id").nullable is True
    assert _on_delete("reporter_user_id") == "SET NULL"


def test_a_complaint_about_something_gone_goes_with_it() -> None:
    assert _on_delete("product_id") == "CASCADE"
    assert _on_delete("business_id") == "CASCADE"


def test_the_moderator_who_closed_it_may_go_and_the_decision_stays() -> None:
    assert _on_delete("resolved_by") == "SET NULL"
