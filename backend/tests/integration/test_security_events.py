"""What the platform writes down about security, and who it tells.

The journal is read by one administrator afterwards; the letters are read by the person it
happened to, while it is happening. The second is what catches a stolen password — the thief
has the credentials and the account, and the only thing they do not have is the inbox.

Two kinds of entry are checked here rather than with the feature that produces them, because
what makes them worth having is a property neither feature owns: they have no actor. Every
other line in the journal is somebody doing something and names them; a replayed token was
presented by a party nobody can name, and a bootstrap answers to whoever holds the server.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.mail import Letter
from app.models import AuditLog, Session, User, UserRole
from app.services import notifications
from app.services.admin_bootstrap import bootstrap
from tests.integration.conftest import BUYER_PAYLOAD, csrf_headers, login, register_buyer

pytestmark = pytest.mark.integration

EMAIL = "buyer@example.com"
PASSWORD = str(BUYER_PAYLOAD["password"])
CHOSEN = "a-password-of-my-own-1"
NEW_DEVICE = "Новый вход в аккаунт — AllStore.am"


@pytest.fixture
def letters(monkeypatch: pytest.MonkeyPatch) -> list[Letter]:
    caught: list[Letter] = []

    async def fake_deliver(settings: object, letter: Letter) -> None:
        caught.append(letter)

    monkeypatch.setattr(notifications, "deliver", fake_deliver)
    return caught


def _subjects(letters: list[Letter]) -> list[str]:
    return [letter.subject for letter in letters]


async def _actions(session: AsyncSession) -> list[str]:
    rows = await session.execute(select(AuditLog).order_by(AuditLog.created_at))
    return [row.action for row in rows.scalars().all()]


async def test_a_replayed_token_is_recorded_against_nobody(
    committing_api_client: AsyncClient, fresh_session: AsyncSession
) -> None:
    """Nobody is named, and that is the record being honest: writing the owner in that column
    would say they did it, and the whole reason the entry exists is that somebody else did."""
    settings = get_settings()
    client = committing_api_client
    await register_buyer(client)
    stolen = client.cookies[settings.session_cookie]
    await client.post("/api/v1/auth/renew", headers=csrf_headers(client))
    # the grace window is for two tabs racing, not for a copy kept overnight
    await fresh_session.execute(
        text(
            "UPDATE sessions SET revoked_at = now() - interval '1 hour' "
            "WHERE revoked_at IS NOT NULL"
        )
    )
    await fresh_session.commit()
    client.cookies.set(settings.session_cookie, stolen)

    await client.get("/api/v1/users/me")

    fresh_session.expire_all()
    entries = (await fresh_session.execute(select(AuditLog))).scalars().all()
    replayed = next(entry for entry in entries if entry.action == "session.replayed")
    assert replayed.actor_user_id is None
    # the account it happened to, which is what an administrator searches by
    assert replayed.entity_id is not None
    assert replayed.details["device"]


async def test_the_first_administrator_leaves_an_actorless_trace(session: AsyncSession) -> None:
    """The one appointment the interface cannot make, and therefore the one nobody would
    otherwise be able to account for afterwards."""
    await bootstrap(session, "founder@example.com", "a-deploy-password-1")

    assert await _actions(session) == ["user.admin_bootstrapped"]
    entry = (await session.execute(select(AuditLog))).scalars().one()
    assert entry.actor_user_id is None
    assert entry.details == {"email": "founder@example.com"}


async def test_running_the_bootstrap_again_writes_nothing(session: AsyncSession) -> None:
    """It runs on every deploy. An entry each time would be a journal of deploys."""
    await bootstrap(session, "founder@example.com", "a-deploy-password-1")

    await bootstrap(session, "founder@example.com", "a-deploy-password-1")

    assert await _actions(session) == ["user.admin_bootstrapped"]


async def test_breaking_the_glass_is_recorded_and_ends_every_admin_session(
    session: AsyncSession,
) -> None:
    """The reason anybody runs it is that the account may not be theirs any more, so a new
    password that leaves the intruder signed in answers only half the problem."""
    await bootstrap(session, "founder@example.com", "a-deploy-password-1")
    admin = (await session.execute(select(User).where(User.role == UserRole.ADMIN))).scalars().one()
    later = datetime.now(UTC) + timedelta(days=1)
    session.add(
        Session(
            user_id=admin.id,
            family_id=uuid.uuid4(),
            token_hash=uuid.uuid4().hex,
            idle_expires_at=later,
            absolute_expires_at=later,
        )
    )
    await session.flush()

    await bootstrap(
        session, "founder@example.com", "another-deploy-password-1", reset_password=True
    )

    assert await _actions(session) == ["user.admin_bootstrapped", "user.admin_password_reset"]
    live = await session.execute(
        select(Session).where(Session.user_id == admin.id, Session.revoked_at.is_(None))
    )
    assert live.scalars().all() == []


async def test_the_first_sign_in_does_not_write_to_anybody(
    api_client: AsyncClient, letters: list[Letter]
) -> None:
    """A letter for every one of somebody's own daily logins is a letter they stop reading,
    and then the one that mattered goes unread too."""
    await api_client.post("/api/v1/auth/register/buyer", json=BUYER_PAYLOAD)
    letters.clear()

    await login(api_client, EMAIL, PASSWORD)

    assert NEW_DEVICE not in _subjects(letters)


async def test_opening_the_account_somewhere_else_is_reported(
    api_client: AsyncClient, letters: list[Letter]
) -> None:
    """The account was already open elsewhere, so this one is news — and the news is the only
    thing a thief with the right password cannot stop."""
    await register_buyer(api_client)
    api_client.cookies.clear()
    letters.clear()

    await login(api_client, EMAIL, PASSWORD)

    assert _subjects(letters) == [NEW_DEVICE]
    assert letters[0].to == EMAIL
    assert "/devices" in letters[0].body
    assert "/password/forgot" in letters[0].body


async def test_a_wrong_password_writes_to_nobody(
    api_client: AsyncClient, letters: list[Letter]
) -> None:
    """Otherwise the sign-in form becomes a way to send somebody mail by typing their address."""
    await register_buyer(api_client)
    api_client.cookies.clear()
    letters.clear()

    await login(api_client, EMAIL, "not-the-password")

    assert letters == []


async def test_changing_the_password_is_reported_to_the_owner(
    api_client: AsyncClient, letters: list[Letter]
) -> None:
    """Somebody who did not change it is the only person this concerns."""
    await register_buyer(api_client)
    letters.clear()

    await api_client.post(
        "/api/v1/auth/password",
        json={"current_password": PASSWORD, "password": CHOSEN},
        headers=csrf_headers(api_client),
    )

    assert _subjects(letters) == ["Пароль изменён — AllStore.am"]
    assert "/password/forgot" in letters[0].body
