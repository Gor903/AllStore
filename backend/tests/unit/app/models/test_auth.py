"""The reset link: a hash, an expiry, and one use.

All three matter together. The hash keeps the table from being a list of ways in; the expiry
keeps a forgotten letter from being one next year; and the single use is what makes a link
that was read by somebody else worth nothing the moment its owner uses it.
"""

from app.models.auth import PasswordResetToken
from tests.unit.app.models import column_of, on_delete, table_of


def test_the_table_holds_a_hash_and_never_a_token() -> None:
    assert "token_hash" in table_of(PasswordResetToken).columns
    assert "token" not in table_of(PasswordResetToken).columns
    assert column_of(PasswordResetToken, "token_hash").unique is True


def test_a_link_belongs_to_an_account_and_goes_with_it() -> None:
    assert on_delete(PasswordResetToken, "user_id") == "CASCADE"


def test_a_link_expires_and_is_spent_once() -> None:
    columns = table_of(PasswordResetToken).columns

    assert "expires_at" in columns
    assert "used_at" in columns
