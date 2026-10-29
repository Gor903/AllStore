"""A password somebody else typed stops working.

Before this, "temporary" meant nothing but a flag: the password an administrator read off a
command line six months ago still opened the account, and the one thing known about it is
that somebody other than its owner has seen it.
"""

from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models import User, UserRole
from tests.integration.conftest import STAFF_PASSWORD, csrf_headers, login, seed_staff

pytestmark = pytest.mark.integration

CHOSEN = "a-password-of-my-own-1"


def _long_ago() -> datetime:
    hours = get_settings().handed_over_password_ttl_hours
    return datetime.now(UTC) - timedelta(hours=hours + 1)


async def test_a_fresh_handover_still_opens_the_account(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    moderator = await seed_staff(session, UserRole.MODERATOR, second_factor=False)
    moderator.must_change_password = True
    moderator.password_handed_over_at = datetime.now(UTC)
    await session.flush()

    assert (await login(api_client, moderator.email, STAFF_PASSWORD)).status_code == 200


async def test_an_old_one_does_not(api_client: AsyncClient, session: AsyncSession) -> None:
    moderator = await seed_staff(session, UserRole.MODERATOR, second_factor=False)
    moderator.must_change_password = True
    moderator.password_handed_over_at = _long_ago()
    await session.flush()

    refused = await login(api_client, moderator.email, STAFF_PASSWORD)

    assert refused.status_code == 401
    assert refused.json()["error"]["code"] == "handed_over_password_expired"


async def test_the_refusal_says_what_to_do_about_it(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    """The person it refuses cannot fix it alone — only whoever handed it over can hand over
    another, and a message that does not say so leaves them pressing the button again."""
    moderator = await seed_staff(session, UserRole.MODERATOR, second_factor=False)
    moderator.must_change_password = True
    moderator.password_handed_over_at = _long_ago()
    await session.flush()

    refused = await login(api_client, moderator.email, STAFF_PASSWORD)

    assert "администратора" in refused.json()["error"]["message"]


async def test_a_password_of_their_own_never_goes_stale(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    """The stamp means nothing once they have chosen one, and must not outlive the flag."""
    moderator = await seed_staff(session, UserRole.MODERATOR, second_factor=False)
    moderator.must_change_password = True
    moderator.password_handed_over_at = datetime.now(UTC)
    await session.flush()
    await login(api_client, moderator.email, STAFF_PASSWORD)
    await api_client.post(
        "/api/v1/auth/password",
        json={"current_password": STAFF_PASSWORD, "password": CHOSEN},
        headers=csrf_headers(api_client),
    )

    # re-read rather than refreshed in place: the checker remembers what was assigned above
    # and would call the assertion below impossible
    changed = (await session.execute(select(User).where(User.id == moderator.id))).scalar_one()
    assert changed.must_change_password is False
    assert changed.password_handed_over_at is None

    # and the clock cannot come back to haunt them: there is nothing left for it to measure
    changed.password_handed_over_at = _long_ago()
    await session.flush()
    api_client.cookies.clear()
    assert (await login(api_client, moderator.email, CHOSEN)).status_code == 200


async def test_appointing_a_moderator_starts_the_clock(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    from tests.integration.conftest import act_as

    await act_as(api_client, await seed_staff(session, UserRole.ADMIN))

    await api_client.post(
        "/api/v1/admin/moderators",
        json={"email": "fresh-moderator@example.com", "password": "handed-over-1"},
        headers=csrf_headers(api_client),
    )

    appointed = (
        await session.execute(select(User).where(User.email == "fresh-moderator@example.com"))
    ).scalar_one()
    assert appointed.must_change_password is True
    assert appointed.password_handed_over_at is not None


async def test_break_glass_starts_it_too(session: AsyncSession) -> None:
    """`grant_role --reset-password` hands one over, so it expires like any other."""
    from scripts.grant_role import apply

    moderator = await seed_staff(session, UserRole.MODERATOR, second_factor=False)
    moderator.password_handed_over_at = None
    await session.flush()

    await apply(session, moderator.email, "handed-over-1", UserRole.MODERATOR, reset_password=True)

    await session.refresh(moderator)
    assert moderator.password_handed_over_at is not None


async def test_an_ordinary_account_is_not_affected(api_client: AsyncClient) -> None:
    """Nobody handed them anything, so there is no clock on them at all."""
    from tests.integration.conftest import register_buyer

    await register_buyer(api_client)
    api_client.cookies.clear()

    assert (await login(api_client, "buyer@example.com", "buyer-password-1")).status_code == 200
