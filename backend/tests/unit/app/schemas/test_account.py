"""Taking a person's access away, giving it back, and the record of both.

Blocking is the heaviest thing staff can do to an account, so it carries a reason. Lifting one
does not: the reason is offered, not demanded — somebody restoring access is undoing a
restriction, and making them justify that is a way of discouraging it.

The history is read by people, so it names people by their address rather than by uuid.
"""

import uuid
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.models import AccountBlock, User
from app.schemas.account import AccountBlockRead, BlockRequest, UnblockRequest


def test_taking_access_away_carries_the_reason() -> None:
    assert BlockRequest(reason="Спам в переписке").reason == "Спам в переписке"


@pytest.mark.parametrize("reason", ["", "   "])
def test_a_block_with_nothing_said_is_refused(reason: str) -> None:
    with pytest.raises(ValidationError):
        BlockRequest(reason=reason)


def test_giving_it_back_needs_no_justification() -> None:
    """The reason is offered, not demanded."""
    assert UnblockRequest().reason is None
    assert UnblockRequest(reason="Разобрались").reason == "Разобрались"


@pytest.mark.parametrize("body", [{"reason": "Спам", "user_id": "1"}, {"status": "blocked"}])
def test_neither_form_takes_a_field_nobody_declared(body: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        BlockRequest(**body)


def _block(**overrides: object) -> AccountBlock:
    fields: dict[str, object] = {
        "id": uuid.uuid4(),
        "user_id": uuid.uuid4(),
        "reason": "Спам в переписке",
        "created_at": datetime.now(UTC),
        "revoked_at": None,
        "revoke_reason": None,
    }
    block = AccountBlock(**{**fields, **overrides})
    block.actor = None
    block.revoked_by = None
    return block


def test_a_history_names_people_by_their_address() -> None:
    """A history read by a moderator and full of identifiers is a history nobody can read."""
    block = _block()
    block.actor = User(id=uuid.uuid4(), email="moderator@allstore.am")

    read = AccountBlockRead.from_block(block)

    assert read.actor_email == "moderator@allstore.am"


def test_a_block_whose_author_is_gone_is_still_a_block() -> None:
    """An account that was deleted leaves its decisions behind: the person it was applied to
    has to be able to see that it happened, whoever made it."""
    read = AccountBlockRead.from_block(_block())

    assert read.actor_email is None
    assert read.reason == "Спам в переписке"


def test_a_lifted_block_says_who_lifted_it_and_why() -> None:
    block = _block(revoked_at=datetime.now(UTC), revoke_reason="Разобрались")
    block.revoked_by = User(id=uuid.uuid4(), email="admin@allstore.am")

    read = AccountBlockRead.from_block(block)

    assert read.revoked_by_email == "admin@allstore.am"
    assert read.revoke_reason == "Разобрались"
    assert read.in_force is False


def test_a_block_nobody_lifted_is_the_one_in_force() -> None:
    """`in_force` is the whole question a screen asks of this list — the rest is history."""
    read = AccountBlockRead.from_block(_block())

    assert read.in_force is True
    assert read.revoked_at is None
