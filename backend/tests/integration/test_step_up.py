"""The actions that will not take a session's word for it.

Signing in is a claim that fades. Most of what the platform does is reversible and does not
need the claim renewed — barring an account is undone by unbarring it, a verdict by another
verdict. Appointing a moderator, handing over the administrator role and replacing somebody's
password are not, and a laptop left open in a cafe is the circumstance they are worth
protecting from.
"""

from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Session, User, UserRole
from tests.integration.conftest import STAFF_PASSWORD, act_as, csrf_headers, seed_staff

pytestmark = pytest.mark.integration

VERIFY = "/api/v1/auth/verify"
MODERATORS = "/api/v1/admin/moderators"


async def _stale(session: AsyncSession, user: User) -> None:
    """Pushes the claim far enough into the past that it has faded."""
    rows = (
        (await session.execute(select(Session).where(Session.user_id == user.id))).scalars().all()
    )
    for row in rows:
        row.verified_at = datetime.now(UTC) - timedelta(hours=1)
    await session.flush()


async def _appoint(client: AsyncClient, email: str) -> int:
    response = await client.post(
        MODERATORS,
        json={"email": email, "password": "a-handed-over-password-1"},
        headers=csrf_headers(client),
    )
    return response.status_code


async def test_signing_in_counts_as_proving_it(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    """Otherwise every administrator would type their password twice to do anything, which
    is how a prompt turns into something people click through without reading."""
    admin = await seed_staff(session, UserRole.ADMIN)
    await act_as(api_client, admin)

    assert await _appoint(api_client, "fresh@example.com") == 201


async def test_a_claim_that_faded_is_refused(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    admin = await seed_staff(session, UserRole.ADMIN)
    await act_as(api_client, admin)
    await _stale(session, admin)

    response = await api_client.post(
        MODERATORS,
        json={"email": "stale@example.com", "password": "a-handed-over-password-1"},
        headers=csrf_headers(api_client),
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "verification_required"


async def test_proving_it_again_opens_the_door(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    admin = await seed_staff(session, UserRole.ADMIN)
    await act_as(api_client, admin)
    await _stale(session, admin)

    proved = await api_client.post(
        VERIFY, json={"password": STAFF_PASSWORD}, headers=csrf_headers(api_client)
    )

    assert proved.status_code == 200
    assert await _appoint(api_client, "after@example.com") == 201


async def test_the_wrong_password_proves_nothing(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    admin = await seed_staff(session, UserRole.ADMIN)
    await act_as(api_client, admin)
    await _stale(session, admin)

    refused = await api_client.post(
        VERIFY, json={"password": "not-the-password"}, headers=csrf_headers(api_client)
    )

    assert refused.status_code == 401
    assert await _appoint(api_client, "nope@example.com") == 403


async def test_the_reversible_things_are_left_alone(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    """Barring an account is undone by unbarring it, and a moderator working a queue should
    not be asked for a password every ten minutes to keep doing their job."""
    moderator = await seed_staff(session, UserRole.MODERATOR)
    buyer = User(
        email="barred@example.com",
        password_hash=moderator.password_hash,
        role=UserRole.BUYER,
    )
    session.add(buyer)
    await session.flush()
    await act_as(api_client, moderator)
    await _stale(session, moderator)

    response = await api_client.post(
        f"/api/v1/accounts/{buyer.id}/block",
        json={"reason": "Нарушение правил площадки"},
        headers=csrf_headers(api_client),
    )

    assert response.status_code == 200


async def test_verifying_needs_a_session_of_its_own(api_client: AsyncClient) -> None:
    response = await api_client.post(VERIFY, json={"password": STAFF_PASSWORD})

    assert response.status_code in (401, 403)
