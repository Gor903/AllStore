"""The account table, and the decisions written into it rather than into Python.

Two of them are load-bearing and neither is visible from the code that uses the model:

**One administrator, enforced by a partial unique index.** Every other guard on the role
hierarchy is a check in Python, and two requests can pass the same check in the same moment.
This index is the one that cannot be raced.

**The telephone is not unique, deliberately.** Nobody checks that a number belongs to whoever
typed it, so a unique constraint on it was a way to take something from a stranger: type their
number into the registration form and they can no longer use their own.

The enum values are what is stored in the column. Renaming a member is not a rename — it is a
migration, and without one every existing row stops matching.
"""

from typing import Any

from sqlalchemy import Column

from app.models import User, UserRole, UserStatus
from tests.unit.app.models import (
    column_of,
    default_of,
    index_of,
    server_default_of,
    table_of,
    where_of,
)


def _column(name: str) -> Column[Any]:
    return column_of(User, name)


def test_the_values_the_role_is_stored_as() -> None:
    assert [role.value for role in UserRole] == ["buyer", "seller", "moderator", "admin"]


def test_the_values_the_status_is_stored_as() -> None:
    assert [status.value for status in UserStatus] == ["active", "suspended", "blocked"]


def test_a_new_account_is_a_buyer_and_is_active() -> None:
    """Both defaults are the smallest thing an account can be: a role that may buy and
    nothing else, and a status that is not yet a punishment."""
    assert default_of(User, "role") is UserRole.BUYER
    assert default_of(User, "status") is UserStatus.ACTIVE


def test_there_can_only_be_one_administrator_and_the_database_says_so() -> None:
    """A check in Python passes twice when two requests arrive together; this does not."""
    index = index_of(User, "uq_users_single_admin")

    assert index.unique is True
    assert "role = 'admin'" in where_of(index)


def test_an_address_belongs_to_one_account() -> None:
    assert _column("email").unique is True


def test_a_telephone_number_does_not() -> None:
    """A unique telephone is a way to take one from a stranger: type their number into the
    registration form and they can no longer use their own."""
    assert column_of(User, "phone").unique in (None, False)
    assert _column("phone").index is True


def test_an_account_always_has_a_hash_and_never_a_password() -> None:
    assert "password_hash" in table_of(User).columns
    assert "password" not in table_of(User).columns


def test_a_blocked_account_stops_acting_without_waiting_for_a_token_to_expire() -> None:
    """`is_active` is asked on every authorized request for exactly this reason."""
    allowed = {status: User(status=status).is_active for status in UserStatus}

    assert allowed == {
        UserStatus.ACTIVE: True,
        UserStatus.SUSPENDED: False,
        UserStatus.BLOCKED: False,
    }


def test_an_account_owes_no_password_change_until_somebody_hands_one_over() -> None:
    """A password somebody else chose is not a password — but that is the exception, so the
    column says no by default, in the database as well as in Python."""
    assert default_of(User, "must_change_password") is False
    assert "false" in server_default_of(User, "must_change_password")


def test_the_handover_is_dated_so_that_it_can_stop_working() -> None:
    """A temporary password with no expiry is a permanent one nobody got round to replacing —
    and the whole reason it is marked temporary is that somebody else has seen it."""
    assert "password_handed_over_at" in table_of(User).columns
