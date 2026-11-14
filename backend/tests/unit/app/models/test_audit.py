"""The journal: who did what to whom, and when.

Written by the services that carry out administrative actions and never edited afterwards — a
record that can be corrected is not a record. Hence no `updated_at` at all: there is nothing
here that may be updated.

The timestamp is `clock_timestamp()` rather than `now()`, and that is not pedantry. `now()` is
the time the transaction began, so two entries written in one transaction would share a
timestamp and the journal's order among them would be decided by a random identifier.
"""

from app.models import AuditLog
from tests.unit.app.models import column_of, default_of, on_delete, server_default_of, table_of


def test_nothing_here_may_be_updated() -> None:
    assert "updated_at" not in table_of(AuditLog).columns


def test_an_entry_outlives_the_account_that_made_it() -> None:
    """SET NULL rather than CASCADE: losing the actor must not erase what they did."""
    assert on_delete(AuditLog, "actor_user_id") == "SET NULL"


def test_the_platform_itself_may_be_the_author() -> None:
    """A sweep run by the worker is still worth recording, and it has no account."""
    assert column_of(AuditLog, "actor_user_id").nullable is True


def test_two_entries_in_one_transaction_keep_their_order() -> None:
    """`now()` is the moment the transaction began, so both would carry the same instant and
    the journal would be sorted by a random identifier."""
    default = server_default_of(AuditLog, "created_at")

    assert "clock_timestamp()" in default


def test_the_action_is_searchable_because_the_journal_is_filtered_by_it() -> None:
    assert column_of(AuditLog, "action").index is True
    assert column_of(AuditLog, "entity_id").index is True


def test_the_details_are_a_column_named_metadata_and_an_attribute_that_is_not() -> None:
    """SQLAlchemy keeps `metadata` on every declarative class for the table registry, so the
    attribute could not be called that even though the data model says it is."""
    assert AuditLog.details.property.columns[0].name == "metadata"
    assert "details" not in table_of(AuditLog).columns


def test_an_entry_with_nothing_to_add_still_has_a_place_to_put_it() -> None:
    # wrapped by SQLAlchemy into a context-taking callable; what it yields is the empty object
    assert default_of(AuditLog, "metadata").__wrapped__() == {}
