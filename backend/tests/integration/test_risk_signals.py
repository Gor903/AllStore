"""A session that turns up somewhere it has not been.

Nothing here runs on the stand or in production: no geolocation source is configured, so
`geo.locate` answers nothing and none of this fires. The tests install a source of their own,
because the point of laying the plumbing in now is that it works the day somebody plugs one
in — and code nobody has ever run is code nobody should rely on.
"""

from collections.abc import Iterator

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import geo
from app.core.config import get_settings
from app.core.geo import Place
from app.core.mail import Letter
from app.models import Session
from app.services import notifications
from app.services import sessions as session_service
from tests.integration.conftest import register_buyer

pytestmark = pytest.mark.integration


@pytest.fixture
def somewhere() -> Iterator[dict[str, Place]]:
    """Says where every address is, and lets a test change its mind mid-flight."""
    answer = {"here": Place(country="AM", asn="AS1234")}
    geo.use(lambda ip: answer["here"])
    yield answer
    geo.use(None)


@pytest.fixture
def letters(monkeypatch: pytest.MonkeyPatch) -> list[Letter]:
    caught: list[Letter] = []

    def fake_deliver(settings: object, letter: Letter) -> None:
        caught.append(letter)

    monkeypatch.setattr(notifications, "deliver", fake_deliver)
    return caught


async def test_a_new_session_remembers_where_it_began(
    api_client: AsyncClient, session: AsyncSession, somewhere: dict[str, Place]
) -> None:
    await register_buyer(api_client)

    row = (
        (await session.execute(select(Session).where(Session.revoked_at.is_(None))))
        .scalars()
        .first()
    )
    assert row is not None
    assert (row.country, row.asn) == ("AM", "AS1234")


async def test_with_no_source_the_columns_stay_empty(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    """Which is the state the platform actually ships in."""
    await register_buyer(api_client)

    row = (
        (await session.execute(select(Session).where(Session.revoked_at.is_(None))))
        .scalars()
        .first()
    )
    assert row is not None
    assert (row.country, row.asn) == (None, None)


async def test_turning_up_elsewhere_is_reported(
    committing_api_client: AsyncClient,
    fresh_session: AsyncSession,
    somewhere: dict[str, Place],
    letters: list[Letter],
) -> None:
    client = committing_api_client
    await register_buyer(client)
    letters.clear()
    somewhere["here"] = Place(country="DE", asn="AS9999")

    await client.get("/api/v1/users/me")

    assert [letter.subject for letter in letters] == ["Вход из другого места — AllStore.am"]
    assert "DE" in letters[0].body


async def test_and_is_only_reported_once(
    committing_api_client: AsyncClient,
    fresh_session: AsyncSession,
    somewhere: dict[str, Place],
    letters: list[Letter],
) -> None:
    """The new place is written down, so the next request compares against it. Without that
    every request from the new country would be a fresh alarm."""
    client = committing_api_client
    await register_buyer(client)
    somewhere["here"] = Place(country="DE", asn="AS9999")
    await client.get("/api/v1/users/me")
    letters.clear()

    await client.get("/api/v1/users/me")

    assert letters == []


async def test_moving_withdraws_the_recent_password(
    committing_api_client: AsyncClient,
    fresh_session: AsyncSession,
    somewhere: dict[str, Place],
) -> None:
    """Not a sign-out — people do travel. But the claim that this is the same person is
    exactly what a step-up asks to have renewed."""
    client = committing_api_client
    await register_buyer(client)
    somewhere["here"] = Place(country="DE", asn="AS9999")

    await client.get("/api/v1/users/me")

    # the session is still good: nothing was ended
    assert (await client.get("/api/v1/users/me")).status_code == 200
    fresh_session.expire_all()
    row = (
        (await fresh_session.execute(select(Session).where(Session.revoked_at.is_(None))))
        .scalars()
        .first()
    )
    assert row is not None
    assert not session_service.is_freshly_verified(row, get_settings())


async def test_the_first_place_anybody_can_name_is_not_a_move(
    committing_api_client: AsyncClient,
    fresh_session: AsyncSession,
    letters: list[Letter],
) -> None:
    """A session that began before a source existed has nowhere to have moved from, and
    telling its owner they travelled would be telling them about our deployment."""
    client = committing_api_client
    await register_buyer(client)
    letters.clear()
    geo.use(lambda ip: Place(country="AM", asn="AS1234"))
    try:
        await client.get("/api/v1/users/me")
    finally:
        geo.use(None)

    assert letters == []
    fresh_session.expire_all()
    row = (
        (await fresh_session.execute(select(Session).where(Session.revoked_at.is_(None))))
        .scalars()
        .first()
    )
    assert row is not None
    assert row.country == "AM"
