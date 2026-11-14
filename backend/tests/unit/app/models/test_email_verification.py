"""The letter that proves an address answers.

The token is stored as a hash: a table of live links is a table of ways into accounts, and
these links arrive in inboxes that are not always the owner's any more.
"""

from app.models import EmailVerification
from tests.unit.app.models import column_of, on_delete, table_of


def test_the_table_holds_a_hash_and_never_a_token() -> None:
    assert "token_hash" in table_of(EmailVerification).columns
    assert "token" not in table_of(EmailVerification).columns
    assert column_of(EmailVerification, "token_hash").unique is True


def test_a_link_belongs_to_an_account_and_goes_with_it() -> None:
    assert on_delete(EmailVerification, "user_id") == "CASCADE"


def test_a_link_expires_and_is_spent_once() -> None:
    columns = table_of(EmailVerification).columns

    assert "expires_at" in columns
    assert "used_at" in columns


def test_the_address_it_is_about_travels_with_it() -> None:
    """A change of login is confirmed at the new address, which is not yet on the account —
    so the row has to carry it rather than read it off the user."""
    assert "email" in table_of(EmailVerification).columns
