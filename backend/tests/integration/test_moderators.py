"""Appointing a moderator: the administrator makes the account, the moderator claims it.

There is one way into the role and it starts with an administrator typing an address. The
password they type is one they know, so the account is not yet anybody's until the moderator
replaces it — that is what makes it safe to send in a chat message.
"""

import uuid

import pytest
from httpx import AsyncClient, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import verify_password
from app.models import AuditLog, User, UserRole
from app.services.auth import password_of
from tests.integration.conftest import act_as, csrf_headers, login, register_buyer, seed_staff

pytestmark = pytest.mark.integration

MODERATORS = "/api/v1/admin/moderators"
HANDED_OVER = "handed-over-password-1"
CHOSEN = "a-password-of-my-own-1"


def an_email() -> str:
    return f"moderator-{uuid.uuid4().hex}@example.com"


async def create(client: AsyncClient, email: str, password: str = HANDED_OVER) -> Response:
    return await client.post(
        MODERATORS, json={"email": email, "password": password}, headers=csrf_headers(client)
    )


async def test_the_administrator_appoints_a_moderator(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    await act_as(api_client, await seed_staff(session, UserRole.ADMIN))
    email = an_email()

    response = await create(api_client, email)

    assert response.status_code == 201
    body = response.json()
    assert body["role"] == "moderator"
    assert body["email"] == email
    # handed over, therefore temporary
    assert body["must_change_password"] is True


async def test_the_address_is_normalized(api_client: AsyncClient, session: AsyncSession) -> None:
    await act_as(api_client, await seed_staff(session, UserRole.ADMIN))
    email = an_email()

    response = await create(api_client, f"  {email.upper()}  ")

    assert response.json()["email"] == email


async def test_a_taken_address_is_refused(api_client: AsyncClient, session: AsyncSession) -> None:
    await register_buyer(api_client)
    await act_as(api_client, await seed_staff(session, UserRole.ADMIN))

    response = await create(api_client, "buyer@example.com")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "account_exists"


async def test_the_new_moderator_gets_in_once_and_no_further(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    await act_as(api_client, await seed_staff(session, UserRole.ADMIN))
    email = an_email()
    await create(api_client, email)

    api_client.cookies.clear()
    assert (await login(api_client, email, HANDED_OVER)).status_code == 200
    refused = await api_client.get("/api/v1/moderation/products")

    assert refused.status_code == 403
    assert refused.json()["error"]["code"] == "password_change_required"


async def test_choosing_a_password_opens_the_queue(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    await act_as(api_client, await seed_staff(session, UserRole.ADMIN))
    email = an_email()
    await create(api_client, email)

    api_client.cookies.clear()
    await login(api_client, email, HANDED_OVER)
    await api_client.post(
        "/api/v1/auth/password",
        json={"current_password": HANDED_OVER, "password": CHOSEN},
        headers=csrf_headers(api_client),
    )
    api_client.cookies.clear()
    await login(api_client, email, CHOSEN)

    assert (await api_client.get("/api/v1/moderation/products")).status_code == 200


async def test_a_moderator_cannot_appoint_another(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    """One who could appoint moderators would be an administrator under another name."""
    await act_as(api_client, await seed_staff(session, UserRole.MODERATOR))

    assert (await create(api_client, an_email())).status_code == 403


async def test_a_buyer_cannot_appoint_anybody(api_client: AsyncClient) -> None:
    await register_buyer(api_client)

    assert (await create(api_client, an_email())).status_code == 403


async def test_the_appointment_reaches_the_journal(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    await act_as(api_client, await seed_staff(session, UserRole.ADMIN))
    email = an_email()

    await create(api_client, email)

    entries = (await session.execute(select(AuditLog))).scalars().all()
    appointed = next(entry for entry in entries if entry.action == "moderator.created")
    assert appointed.details["email"] == email


async def test_a_lost_password_is_replaced_by_the_administrator(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    """No recovery link: the administrator already decides who moderates."""
    await act_as(api_client, await seed_staff(session, UserRole.ADMIN))
    email = an_email()
    created = (await create(api_client, email)).json()

    response = await api_client.post(
        f"{MODERATORS}/{created['id']}/password",
        json={"password": "second-handover-1"},
        headers=csrf_headers(api_client),
    )

    assert response.status_code == 200
    user = (await session.execute(select(User).where(User.email == email))).scalars().one()
    await session.refresh(user)
    assert verify_password("second-handover-1", password_of(user))
    # handed over again, so it expires again
    assert user.must_change_password is True


async def test_a_reset_aimed_at_somebody_who_is_not_a_moderator_finds_nobody(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    admin = await seed_staff(session, UserRole.ADMIN)
    await act_as(api_client, admin)

    response = await api_client.post(
        f"{MODERATORS}/{admin.id}/password",
        json={"password": "not-happening-1"},
        headers=csrf_headers(api_client),
    )

    assert response.status_code == 404


async def test_a_short_password_is_refused(api_client: AsyncClient, session: AsyncSession) -> None:
    await act_as(api_client, await seed_staff(session, UserRole.ADMIN))

    assert (await create(api_client, an_email(), "short")).status_code == 422
