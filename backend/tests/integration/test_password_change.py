"""A password somebody else chose gets the owner in once, and no further.

The case this exists for is the administrator created from `ADMIN_PASSWORD`: that password is
known to everyone who can read the deploy variables, so an account still carrying it is not
yet anybody's. The refusal is on the server, on every route, rather than in a screen the
client could skip.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import verify_password
from app.models import AuditLog, Session, User, UserRole
from tests.integration.conftest import csrf_headers, login, register_buyer

pytestmark = pytest.mark.integration

EMAIL = "buyer@example.com"
PASSWORD = "buyer-password-1"
CHOSEN = "a-password-of-my-own-1"

CHANGE_URL = "/api/v1/auth/password"


async def owing_a_change(client: AsyncClient, session: AsyncSession) -> User:
    """A registered account that has been handed its password rather than choosing it."""
    await register_buyer(client)
    user = (await session.execute(select(User).where(User.email == EMAIL))).scalars().one()
    user.must_change_password = True
    await session.flush()
    return user


async def test_an_owed_password_blocks_the_rest_of_the_site(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    await owing_a_change(api_client, session)

    response = await api_client.get("/api/v1/users/me/business")

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "password_change_required"


async def test_a_route_that_asks_for_nothing_is_closed(session: AsyncSession) -> None:
    """The allowance is asked for by type, so forgetting to ask locks a door.

    It used to be a suffix match on the path, and this route is the shape that defeated it:
    it ends in `/users/me`, which was on the allowed list, without being that route or having
    anybody decide it should be let through.
    """
    from httpx import ASGITransport

    from app.db.session import get_session
    from app.deps.auth import CurrentUser
    from app.main import create_app

    app = create_app()

    @app.get("/api/v1/decoy/users/me")
    async def decoy(user: CurrentUser) -> dict[str, str]:
        return {"email": user.email}

    async def _use_test_session() -> AsyncSession:
        return session

    app.dependency_overrides[get_session] = _use_test_session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await owing_a_change(client, session)

        response = await client.get("/api/v1/decoy/users/me")

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "password_change_required"


async def test_the_owner_can_still_ask_who_they_are(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    """Otherwise the client has no way to learn why everything else is refusing it."""
    await owing_a_change(api_client, session)

    response = await api_client.get("/api/v1/users/me")

    assert response.status_code == 200
    assert response.json()["must_change_password"] is True


async def test_the_owner_can_still_leave(api_client: AsyncClient, session: AsyncSession) -> None:
    await owing_a_change(api_client, session)

    response = await api_client.post(
        "/api/v1/auth/logout", headers=csrf_headers(api_client), json={}
    )

    assert response.status_code == 204


async def test_choosing_a_password_opens_the_site(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    user = await owing_a_change(api_client, session)

    change = await api_client.post(
        CHANGE_URL,
        json={"current_password": PASSWORD, "password": CHOSEN},
        headers=csrf_headers(api_client),
    )

    assert change.status_code == 200
    await session.refresh(user)
    assert user.must_change_password is False
    assert verify_password(CHOSEN, user.password_hash)


async def test_the_old_password_has_to_be_known(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    """A session left open on somebody else's screen must not be enough to take the account."""
    user = await owing_a_change(api_client, session)

    response = await api_client.post(
        CHANGE_URL,
        json={"current_password": "not-the-one-1", "password": CHOSEN},
        headers=csrf_headers(api_client),
    )

    assert response.status_code == 401
    await session.refresh(user)
    assert user.must_change_password is True


async def test_the_change_ends_every_session(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    user = await owing_a_change(api_client, session)

    await api_client.post(
        CHANGE_URL,
        json={"current_password": PASSWORD, "password": CHOSEN},
        headers=csrf_headers(api_client),
    )

    live = await session.execute(
        select(Session).where(Session.user_id == user.id, Session.revoked_at.is_(None))
    )
    assert live.scalars().all() == []


async def test_an_account_owing_nothing_is_not_asked_for_anything(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    """The gate must be invisible to everybody it is not for.

    Checked by the code rather than the status: this route is a seller's, so a buyer is
    refused either way, and only the reason tells the two refusals apart.
    """
    await register_buyer(api_client)

    response = await api_client.get("/api/v1/users/me/business")

    assert response.json()["error"]["code"] != "password_change_required"


async def test_changing_the_login_needs_the_password_and_ends_the_sessions(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    await register_buyer(api_client)
    user = (await session.execute(select(User).where(User.email == EMAIL))).scalars().one()

    response = await api_client.post(
        "/api/v1/auth/email",
        json={"email": "moved@example.com", "current_password": PASSWORD},
        headers=csrf_headers(api_client),
    )

    assert response.status_code == 200
    await session.refresh(user)
    assert user.email == "moved@example.com"
    live = await session.execute(
        select(Session).where(Session.user_id == user.id, Session.revoked_at.is_(None))
    )
    assert live.scalars().all() == []


async def test_the_address_it_already_is_gets_refused(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    """Accepting it would end every session and report a change that did not happen.

    That is how somebody who came to change their password ends up logged out with nothing
    altered — the form asked for a password, so it looked like the right one.
    """
    await register_buyer(api_client)
    user = (await session.execute(select(User).where(User.email == EMAIL))).scalars().one()

    response = await api_client.post(
        "/api/v1/auth/email",
        json={"email": EMAIL, "current_password": PASSWORD},
        headers=csrf_headers(api_client),
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "same_email"
    live = await session.execute(
        select(Session).where(Session.user_id == user.id, Session.revoked_at.is_(None))
    )
    # the sessions are untouched: nothing happened, so nothing ends
    assert live.scalars().all() != []


async def test_a_taken_address_is_refused(api_client: AsyncClient, session: AsyncSession) -> None:
    await register_buyer(api_client)
    session.add(User(email="taken@example.com", password_hash="x", role=UserRole.BUYER))
    await session.flush()

    response = await api_client.post(
        "/api/v1/auth/email",
        json={"email": "taken@example.com", "current_password": PASSWORD},
        headers=csrf_headers(api_client),
    )

    assert response.status_code == 409


async def test_both_changes_reach_the_journal(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    """The administrator's window on the platform has to show credentials moving too."""
    await register_buyer(api_client)

    await api_client.post(
        CHANGE_URL,
        json={"current_password": PASSWORD, "password": CHOSEN},
        headers=csrf_headers(api_client),
    )
    await api_client.post("/api/v1/auth/login", json={"email": EMAIL, "password": CHOSEN})
    await api_client.post(
        "/api/v1/auth/email",
        json={"email": "moved@example.com", "current_password": CHOSEN},
        headers=csrf_headers(api_client),
    )

    entries = (await session.execute(select(AuditLog))).scalars().all()
    actions = {entry.action for entry in entries}
    assert "user.password_changed" in actions
    assert "user.email_changed" in actions
    moved = next(entry for entry in entries if entry.action == "user.email_changed")
    # what it was, because after the write nobody can tell any more
    assert moved.details["from"] == EMAIL


async def test_a_change_without_the_flag_is_an_ordinary_thing_to_do(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    await register_buyer(api_client)

    change = await api_client.post(
        CHANGE_URL,
        json={"current_password": PASSWORD, "password": CHOSEN},
        headers=csrf_headers(api_client),
    )

    assert change.status_code == 200
    api_client.cookies.clear()
    assert (await login(api_client, EMAIL, CHOSEN)).status_code == 200
