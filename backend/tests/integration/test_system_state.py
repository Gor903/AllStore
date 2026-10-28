"""The state of the machine and of the platform, read at the moment it is asked for.

Nothing here is stored, so there is nothing to go stale and nothing to clean up. What the
tests pin down is the shape and the arithmetic — the absolute values belong to whatever
machine is running, and asserting on those would make this suite a weather report.
"""

from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models import User, UserRole
from tests.integration.conftest import act_as, register_buyer, seed_staff

pytestmark = pytest.mark.integration

SYSTEM = "/api/v1/admin/system"
ACTIVITY = "/api/v1/admin/activity"


async def test_the_state_reports_the_machine_and_the_platform(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    await act_as(api_client, await seed_staff(session, UserRole.ADMIN))

    body = (await api_client.get(SYSTEM)).json()

    # the machine: plausible rather than exact, because the exact value is the machine's
    assert 0 <= body["cpu_percent"] <= 100
    assert body["memory_total_mb"] > 0
    assert body["memory_used_mb"] <= body["memory_total_mb"]
    assert body["disk_free_gb"] <= body["disk_total_gb"]
    assert body["uptime_seconds"] > 0
    # the platform: at least the administrator who is asking
    assert body["users"] >= 1
    assert body["database_size_mb"] > 0


async def test_a_live_session_is_counted(api_client: AsyncClient, session: AsyncSession) -> None:
    admin = await seed_staff(session, UserRole.ADMIN)
    await act_as(api_client, admin)

    before = (await api_client.get(SYSTEM)).json()["live_sessions"]
    # logging in again issues another refresh token, which is what a session is here
    await act_as(api_client, admin)
    after = (await api_client.get(SYSTEM)).json()["live_sessions"]

    assert after == before + 1


async def test_the_state_is_the_administrators_alone(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    """How loaded the machine is says nothing about moderating, and plenty about the platform."""
    await act_as(api_client, await seed_staff(session, UserRole.MODERATOR))

    assert (await api_client.get(SYSTEM)).status_code == 403
    assert (await api_client.get(ACTIVITY)).status_code == 403


async def test_a_buyer_reaches_neither(api_client: AsyncClient) -> None:
    await register_buyer(api_client)

    assert (await api_client.get(SYSTEM)).status_code == 403


async def test_activity_returns_every_day_asked_for(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    await act_as(api_client, await seed_staff(session, UserRole.ADMIN))

    body = (await api_client.get(f"{ACTIVITY}?days=7")).json()

    assert len(body["days"]) == 7
    days = [entry["day"] for entry in body["days"]]
    # oldest first, and no holes: a hole would read as a day that was not collected
    assert days == sorted(days)
    assert len(set(days)) == 7


async def test_a_quiet_day_says_zero_rather_than_going_missing(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    await act_as(api_client, await seed_staff(session, UserRole.ADMIN))

    body = (await api_client.get(f"{ACTIVITY}?days=30")).json()

    # thirty days back the stand was empty; those days must be present and zeroed
    assert body["days"][0]["registrations"] == 0
    assert all(set(entry) >= {"day", "registrations", "logins"} for entry in body["days"])


async def test_todays_registration_lands_on_today(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    admin = await seed_staff(session, UserRole.ADMIN)
    session.add(
        User(
            email="counted-today@example.com",
            password_hash=hash_password("activity-password-1"),
            role=UserRole.BUYER,
        )
    )
    await session.flush()
    await act_as(api_client, admin)

    body = (await api_client.get(f"{ACTIVITY}?days=2")).json()

    today = datetime.now(UTC).date().isoformat()
    counted = next(entry for entry in body["days"] if entry["day"] == today)
    assert counted["registrations"] >= 1


async def test_an_account_that_never_came_back_counts_on_no_day(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    """A NULL groups to nothing rather than to a day, which is the right answer."""
    admin = await seed_staff(session, UserRole.ADMIN)
    session.add(
        User(
            email="never-logged-in@example.com",
            password_hash=hash_password("activity-password-1"),
            role=UserRole.BUYER,
            created_at=datetime.now(UTC) - timedelta(days=3),
        )
    )
    await session.flush()
    await act_as(api_client, admin)

    body = (await api_client.get(f"{ACTIVITY}?days=5")).json()

    assert sum(entry["logins"] for entry in body["days"]) >= 1
    assert all(entry["logins"] >= 0 for entry in body["days"])


async def test_the_window_is_bounded(api_client: AsyncClient, session: AsyncSession) -> None:
    await act_as(api_client, await seed_staff(session, UserRole.ADMIN))

    assert (await api_client.get(f"{ACTIVITY}?days=0")).status_code == 422
    assert (await api_client.get(f"{ACTIVITY}?days=365")).status_code == 422
