"""The tenant of a dashboard request.

Resolved from the session and never from the Host. Every seller-facing query filters on the
business this returns, so a forged Host header or a guessed identifier in a path cannot reach
another seller's data — the request simply resolves to the business of whoever is signed in.

A seller with no business is a 404 rather than a 500: the role can be granted from the server
shell, which leaves an account that is a seller and has nothing to sell from.
"""

import uuid
from typing import Any

import pytest

from app.core.errors import NotFoundError
from app.deps.business import get_current_business
from app.models import Business, User, UserRole
from app.repositories import users as users_repo


def _seller() -> User:
    return User(id=uuid.uuid4(), email="seller@example.am", role=UserRole.SELLER)


async def test_the_business_is_the_one_the_signed_in_account_owns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seller = _seller()
    asked: list[uuid.UUID] = []
    shop = Business(id=uuid.uuid4(), legal_name="ООО Ромашка", display_name="Ромашка")

    async def _owned(session: Any, user_id: uuid.UUID) -> Business:
        asked.append(user_id)
        return shop

    monkeypatch.setattr(users_repo, "get_business_of", _owned)

    assert await get_current_business(seller, None) is shop  # type: ignore[arg-type]
    assert asked == [seller.id], "resolved from the session, not from anything in the request"


async def test_a_seller_with_nothing_to_sell_from_is_a_404(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A role granted from the server shell leaves exactly this account, and the cabinet
    sends it to the form that asks the two questions."""

    async def _none(session: Any, user_id: uuid.UUID) -> None:
        return None

    monkeypatch.setattr(users_repo, "get_business_of", _none)

    with pytest.raises(NotFoundError, match="нет бизнеса"):
        await get_current_business(_seller(), None)  # type: ignore[arg-type]
