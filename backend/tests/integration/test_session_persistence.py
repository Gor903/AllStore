"""What a session writes on the way in, and whether it survives a request that writes nothing.

The rule everywhere else is that the commit belongs to the API layer. A session dependency
runs before any of that, on requests that are overwhelmingly reads and commit nothing at all —
so everything it wrote used to be rolled back when the connection closed.

That was not a tidiness problem. A renewal handed the browser a new token and then threw away
the row the token named, and the next request was a 401. Sessions quietly died an hour after
they began, for anybody whose next click happened to be a read.
"""

from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models import Session
from tests.integration.conftest import register_buyer

pytestmark = pytest.mark.integration


# The two columns these tests reach back in time, named rather than passed in: the statement
# is built by interpolation and a parameter would be one the caller could put anything in.
AGEABLE = {
    "created_at": "UPDATE sessions SET created_at = :at WHERE revoked_at IS NULL",
    "last_seen_at": "UPDATE sessions SET last_seen_at = :at WHERE revoked_at IS NULL",
}


async def _age_the_sessions(session: AsyncSession, column: str, by: timedelta) -> None:
    """An absolute moment rather than an interval: the driver binds a timedelta as `interval`,
    and Postgres will not subtract one from a timestamp column without being told to cast."""
    await session.execute(text(AGEABLE[column]), {"at": datetime.now(UTC) - by})
    await session.commit()


async def test_a_renewal_on_a_read_does_not_sign_anybody_out(
    committing_api_client: AsyncClient, fresh_session: AsyncSession
) -> None:
    """The bug this file exists for: the cookie was replaced and the row behind it was not."""
    client = committing_api_client
    await register_buyer(client)
    await _age_the_sessions(fresh_session, "created_at", timedelta(hours=2))

    # a read, which commits nothing of its own — and which is due a renewal
    assert (await client.get("/api/v1/users/me")).status_code == 200

    # the very next request, carrying the token that read was given
    assert (await client.get("/api/v1/users/me")).status_code == 200


async def test_the_idle_clock_actually_moves(
    committing_api_client: AsyncClient, fresh_session: AsyncSession
) -> None:
    """Otherwise the sliding window is a number in a settings file and nothing else: a person
    who only reads would be signed out as if they had been away."""
    client = committing_api_client
    await register_buyer(client)
    await _age_the_sessions(fresh_session, "last_seen_at", timedelta(minutes=10))
    before = (
        (
            await fresh_session.execute(
                select(Session.last_seen_at).where(Session.revoked_at.is_(None))
            )
        )
        .scalars()
        .first()
    )

    await client.get("/api/v1/users/me")

    fresh_session.expire_all()
    after = (
        (
            await fresh_session.execute(
                select(Session.last_seen_at).where(Session.revoked_at.is_(None))
            )
        )
        .scalars()
        .first()
    )
    assert before is not None and after is not None
    assert after > before


async def test_a_read_a_second_later_writes_nothing(
    committing_api_client: AsyncClient, fresh_session: AsyncSession
) -> None:
    """The throttle is what keeps this from turning a read-mostly table into a write-mostly
    one — and now also what keeps it to one commit a minute per session."""
    client = committing_api_client
    await register_buyer(client)
    await client.get("/api/v1/users/me")
    fresh_session.expire_all()
    before = (
        (
            await fresh_session.execute(
                select(Session.last_seen_at).where(Session.revoked_at.is_(None))
            )
        )
        .scalars()
        .first()
    )

    await client.get("/api/v1/users/me")

    fresh_session.expire_all()
    after = (
        (
            await fresh_session.execute(
                select(Session.last_seen_at).where(Session.revoked_at.is_(None))
            )
        )
        .scalars()
        .first()
    )
    assert after == before


async def test_a_session_that_was_renewed_keeps_its_place(
    committing_api_client: AsyncClient, fresh_session: AsyncSession
) -> None:
    """The successor is the same device: losing where it was would make the next request look
    like a move to anybody comparing."""
    client = committing_api_client
    await register_buyer(client)
    await fresh_session.execute(
        text("UPDATE sessions SET country = 'AM', asn = 'AS1234' WHERE revoked_at IS NULL")
    )
    await _age_the_sessions(fresh_session, "created_at", timedelta(hours=2))

    await client.get("/api/v1/users/me")

    fresh_session.expire_all()
    live = (
        (await fresh_session.execute(select(Session).where(Session.revoked_at.is_(None))))
        .scalars()
        .all()
    )
    assert [(row.country, row.asn) for row in live] == [("AM", "AS1234")]


async def test_an_expired_session_is_still_refused(
    committing_api_client: AsyncClient, fresh_session: AsyncSession
) -> None:
    """Committing what the dependency wrote must not turn an expiry into a renewal."""
    client = committing_api_client
    await register_buyer(client)
    expired = datetime.now(UTC) - timedelta(minutes=1)
    await fresh_session.execute(
        text("UPDATE sessions SET idle_expires_at = :at WHERE revoked_at IS NULL"), {"at": expired}
    )
    await fresh_session.commit()

    refused = await client.get("/api/v1/users/me")

    assert refused.status_code == 401
    assert refused.json()["error"]["code"] == "session_expired"


async def test_signing_out_still_ends_the_session(
    committing_api_client: AsyncClient,
) -> None:
    """A commit on the way in must not resurrect anything on the way out."""
    settings = get_settings()
    client = committing_api_client
    await register_buyer(client)

    await client.post(
        "/api/v1/auth/logout",
        headers={settings.csrf_header_name: client.cookies[settings.csrf_cookie]},
    )

    assert (await client.get("/api/v1/users/me")).status_code == 401
