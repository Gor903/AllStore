"""Every ban an account has ever had, and the rules the database keeps about them.

Nothing here is ever deleted. `user_id` is RESTRICT rather than CASCADE precisely so that it
cannot be: a ban that disappears along with the account it was about is not a record. The
moderator's own account may go — SET NULL — because the record of what they decided may not.

One ban in force per account, by a partial unique index: two moderators deciding in the same
moment produce one row and one refusal, rather than two bans that each need lifting.
"""

from datetime import UTC, datetime

from app.models import AccountBlock
from tests.unit.app.models import check_of, column_of, index_of, table_of, where_of


def _on_delete(column: str) -> str | None:
    key = next(k for k in table_of(AccountBlock).foreign_keys if k.parent.name == column)
    return key.ondelete


def test_a_ban_outlives_the_account_it_was_about() -> None:
    """RESTRICT: the row cannot be deleted while a ban points at it, so the history of a
    person cannot be erased by deleting the person."""
    assert _on_delete("user_id") == "RESTRICT"


def test_a_ban_outlives_the_moderator_who_decided_it() -> None:
    """SET NULL on both: the account may go, the decision stays, and the screen says
    "аккаунт удалён" rather than losing the row."""
    assert _on_delete("actor_user_id") == "SET NULL"
    assert _on_delete("revoked_by_user_id") == "SET NULL"


def test_one_ban_in_force_per_account() -> None:
    index = index_of(AccountBlock, "uq_account_blocks_in_force")

    assert index.unique is True
    assert "revoked_at IS NULL" in where_of(index)


def test_a_reason_of_whitespace_is_not_a_reason() -> None:
    """A ban nobody can read a reason for is one the person cannot answer. `\\S` means at
    least one non-whitespace character, so a line of spaces is refused by the database as
    well as by the schema."""
    assert r"\S" in check_of(AccountBlock, "ck_account_blocks_reason")


def test_lifting_one_needs_no_justification() -> None:
    """Unlike the ban itself: the reason is offered, not demanded."""
    assert column_of(AccountBlock, "reason").nullable is False
    assert column_of(AccountBlock, "revoke_reason").nullable is True


def test_a_ban_nobody_lifted_is_the_one_in_force() -> None:
    block = AccountBlock(revoked_at=None)
    assert block.in_force is True

    block.revoked_at = datetime.now(UTC)
    assert block.in_force is False
