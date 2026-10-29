"""What a session is worth, and what ends it.

The subject changed under these tests: there used to be a short JWT and a long refresh token,
and now there is one opaque session the server can withdraw. What they check did not change —
a block takes effect at once, a forged token opens nothing, and a token used by two parties
costs that device its whole family.
"""

from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models import Session, User, UserStatus
from tests.integration.conftest import csrf_headers, register_buyer

pytestmark = pytest.mark.integration


async def test_me_requires_authentication(api_client: AsyncClient) -> None:
    response = await api_client.get("/api/v1/users/me")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "authentication_failed"


async def test_me_returns_the_logged_in_user(api_client: AsyncClient) -> None:
    await register_buyer(api_client)

    response = await api_client.get("/api/v1/users/me")

    assert response.status_code == 200
    assert response.json()["email"] == "buyer@example.com"


async def test_a_token_nobody_issued_opens_nothing(api_client: AsyncClient) -> None:
    settings = get_settings()
    await register_buyer(api_client)
    api_client.cookies.set(settings.session_cookie, "not-a-token-we-ever-handed-out")

    response = await api_client.get("/api/v1/users/me")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_session"


async def test_blocking_an_account_takes_effect_at_once(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    """The session is still perfectly valid, so the status is what must stop the request."""
    await register_buyer(api_client)
    user = (await session.execute(select(User))).scalars().first()
    assert user is not None
    user.status = UserStatus.BLOCKED
    await session.flush()

    response = await api_client.get("/api/v1/users/me")

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "account_not_active"


async def test_a_session_that_sat_too_long_is_refused(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    await register_buyer(api_client)
    row = (await session.execute(select(Session))).scalar_one()
    row.idle_expires_at = datetime.now(UTC) - timedelta(seconds=1)
    await session.flush()

    response = await api_client.get("/api/v1/users/me")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "session_expired"


async def test_the_absolute_clock_ends_a_session_however_busy_it_is(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    """The sliding clock is pushed forward by use; this one is not, which is the point."""
    await register_buyer(api_client)
    row = (await session.execute(select(Session))).scalar_one()
    row.absolute_expires_at = datetime.now(UTC) - timedelta(seconds=1)
    row.idle_expires_at = datetime.now(UTC) + timedelta(days=30)
    await session.flush()

    response = await api_client.get("/api/v1/users/me")

    assert response.status_code == 401


async def test_renewing_keeps_the_device_and_changes_the_token(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    settings = get_settings()
    await register_buyer(api_client)
    first = api_client.cookies[settings.session_cookie]

    response = await api_client.post("/api/v1/auth/renew", headers=csrf_headers(api_client))

    assert response.status_code == 200
    assert api_client.cookies[settings.session_cookie] != first
    rows = (await session.execute(select(Session))).scalars().all()
    assert len(rows) == 2
    # one device, two tokens: the family is what "this device" means
    assert len({row.family_id for row in rows}) == 1
    retired = next(row for row in rows if row.revoked_at is not None)
    assert retired.replaced_by_id is not None


async def test_the_csrf_token_survives_a_renewal(api_client: AsyncClient) -> None:
    """It is derived from the family, not drawn fresh each time, so a tab that cached it does
    not start failing the moment the session renews underneath it."""
    settings = get_settings()
    await register_buyer(api_client)
    before = api_client.cookies[settings.csrf_cookie]

    await api_client.post("/api/v1/auth/renew", headers=csrf_headers(api_client))

    assert api_client.cookies[settings.csrf_cookie] == before


async def test_replaying_a_retired_token_kills_the_whole_device(
    committing_api_client: AsyncClient, fresh_session: AsyncSession
) -> None:
    """A token that comes back after its replacement was issued was held by two parties.

    Read from outside the request on purpose: the refusal was never in doubt, what matters is
    that the revocation it triggers is still there afterwards.
    """
    settings = get_settings()
    client = committing_api_client
    await register_buyer(client)
    stolen = client.cookies[settings.session_cookie]
    await client.post("/api/v1/auth/renew", headers=csrf_headers(client))
    # pushed well past the grace window, so this cannot be read as a tab arriving late
    await fresh_session.execute(
        text(
            "UPDATE sessions SET revoked_at = now() - interval '1 hour' "
            "WHERE revoked_at IS NOT NULL"
        )
    )
    await fresh_session.commit()
    client.cookies.set(settings.session_cookie, stolen)

    response = await client.get("/api/v1/users/me")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_session"
    fresh_session.expire_all()
    rows = (await fresh_session.execute(select(Session))).scalars().all()
    assert len(rows) == 2
    assert all(row.revoked_at is not None for row in rows)


async def test_a_tab_that_was_a_moment_late_is_still_served(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    """Two tabs can send a request in the same instant; one renews and the other arrives
    holding a token retired a moment ago. They share a cookie jar, so the second already has
    the replacement — refusing it would sign somebody out for using two tabs."""
    settings = get_settings()
    await register_buyer(api_client)
    older = api_client.cookies[settings.session_cookie]
    await api_client.post("/api/v1/auth/renew", headers=csrf_headers(api_client))
    api_client.cookies.set(settings.session_cookie, older)

    response = await api_client.get("/api/v1/users/me")

    assert response.status_code == 200
    rows = (await session.execute(select(Session))).scalars().all()
    assert any(row.revoked_at is None for row in rows), "the family must survive a late tab"


async def test_signing_out_ends_the_session(api_client: AsyncClient) -> None:
    await register_buyer(api_client)
    headers = csrf_headers(api_client)

    assert (await api_client.post("/api/v1/auth/logout", headers=headers)).status_code == 204

    assert (await api_client.get("/api/v1/users/me")).status_code == 401


async def test_signing_out_twice_is_not_an_error(api_client: AsyncClient) -> None:
    """Whatever else happens, the button that says "sign out" must not refuse."""
    settings = get_settings()
    await register_buyer(api_client)
    headers = csrf_headers(api_client)
    token = api_client.cookies[settings.session_cookie]
    csrf = api_client.cookies[settings.csrf_cookie]
    await api_client.post("/api/v1/auth/logout", headers=headers)
    api_client.cookies.set(settings.session_cookie, token)
    api_client.cookies.set(settings.csrf_cookie, csrf)

    response = await api_client.post("/api/v1/auth/logout", headers=headers)

    assert response.status_code == 204


async def test_renewing_without_the_csrf_header_is_refused(api_client: AsyncClient) -> None:
    await register_buyer(api_client)

    response = await api_client.post("/api/v1/auth/renew")

    assert response.status_code == 403


async def test_a_planted_csrf_token_is_refused(api_client: AsyncClient) -> None:
    """Satisfying the double submit is not enough: the value has to be the one this device
    should be carrying, and only the server can work out what that is."""
    settings = get_settings()
    await register_buyer(api_client)
    planted = "a" * 64
    api_client.cookies.set(settings.csrf_cookie, planted)

    response = await api_client.post(
        "/api/v1/auth/renew", headers={settings.csrf_header_name: planted}
    )

    assert response.status_code == 403
