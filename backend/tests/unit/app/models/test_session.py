"""A session row: one device, one token, and two clocks.

The token is stored as a hash and nothing else, because a table of live tokens is a table
worth stealing. The family is what makes "this device" a thing one can name at all — it stays
constant across every rotation, so renewing a token does not look like a new sign-in, and
revoking one device means revoking its whole family.

Two clocks, because they answer different questions. The sliding one asks whether the person
is still around; the absolute one puts an end to a session however busy it is, so a token
stolen from an active account does not last forever.
"""

from typing import Any

from sqlalchemy import Column

from app.models import Session
from app.models.session import AuthMethod
from tests.unit.app.models import column_of, table_of


def _column(name: str) -> Column[Any]:
    return column_of(Session, name)


def _on_delete(column: str) -> str | None:
    key = next(k for k in table_of(Session).foreign_keys if k.parent.name == column)
    return key.ondelete


def test_the_table_holds_a_hash_and_never_a_token() -> None:
    assert "token_hash" in table_of(Session).columns
    assert "token" not in table_of(Session).columns
    assert _column("token_hash").unique is True


def test_a_device_is_named_by_its_family_rather_than_by_the_row() -> None:
    """A new sign-in starts a new family; renewing a token stays inside the old one."""
    assert _column("family_id").nullable is False
    assert any(index.name == "ix_sessions_family_id" for index in table_of(Session).indexes)


def test_a_rotated_row_remembers_what_replaced_it() -> None:
    """Which is what makes a replayed token distinguishable from a forged one."""
    assert _on_delete("replaced_by_id") == "SET NULL"


def test_sessions_go_with_the_account() -> None:
    assert _on_delete("user_id") == "CASCADE"


def test_both_clocks_are_required() -> None:
    """A session with no absolute end is one a stolen token keeps alive by being used."""
    assert _column("idle_expires_at").nullable is False
    assert _column("absolute_expires_at").nullable is False


def test_a_device_that_could_not_hold_a_key_is_still_allowed_a_session() -> None:
    """Null costs that session a shorter absolute life rather than the sign-in itself."""
    assert _column("device_public_key").nullable is True


def test_where_a_session_began_is_remembered_and_may_be_unknown() -> None:
    """Null means "nobody knew", not "nowhere": most addresses resolve to nothing useful, and
    a visitor behind a privacy relay is not an intruder."""
    for column in ("ip", "country", "asn", "user_agent"):
        assert _column(column).nullable is True, column


def test_the_newest_accepted_proof_is_kept_so_an_old_one_cannot_be_replayed() -> None:
    assert "last_proof_at" in table_of(Session).columns


def test_the_device_list_is_indexed_the_way_it_is_read() -> None:
    """Newest first per account, which is also the sweep that revokes everything."""
    assert any(index.name == "ix_sessions_user_id_last_seen" for index in table_of(Session).indexes)


def test_the_values_the_way_in_is_stored_as() -> None:
    assert [method.value for method in AuthMethod] == ["password"]
