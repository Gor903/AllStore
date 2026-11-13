"""The second factor: one authenticator per account, and the codes that stand in for it.

Both tables hold hashes. A recovery code is a password by another name — written on paper,
kept for a year, and typed when somebody has already lost their telephone — so a table of
readable ones would be a table worth stealing.

One credential per account, and the codes go with the account: an authenticator that outlived
the account it belonged to would be a key to a door that no longer exists.
"""

from app.models.totp import TotpCredential, TotpRecoveryCode
from tests.unit.app.models import column_of, table_of


def test_one_authenticator_per_account() -> None:
    assert column_of(TotpCredential, "user_id").unique is True


def test_the_secret_and_the_codes_go_with_the_account() -> None:
    for table in (table_of(TotpCredential), table_of(TotpRecoveryCode)):
        key = next(k for k in table.foreign_keys if k.parent.name == "user_id")
        assert key.ondelete == "CASCADE"


def test_a_recovery_code_is_stored_as_a_hash() -> None:
    assert "code_hash" in table_of(TotpRecoveryCode).columns
    assert "code" not in table_of(TotpRecoveryCode).columns
    assert column_of(TotpRecoveryCode, "code_hash").unique is True


def test_a_recovery_code_is_spent_rather_than_deleted() -> None:
    """A used code that disappeared would leave nobody able to say how many are left."""
    assert "used_at" in table_of(TotpRecoveryCode).columns


def test_an_account_may_have_many_codes_and_one_secret() -> None:
    assert column_of(TotpRecoveryCode, "user_id").unique is not True
