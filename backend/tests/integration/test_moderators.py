"""Appointing a moderator: the administrator makes the account, the moderator claims it.

There is one way into the role and it starts with an administrator typing an address — and
nothing else. The password is generated and shown to them once; it is known to somebody other
than its owner, so the account is not yet anybody's until the moderator replaces it, and that
is what makes it safe to send in a chat message.
"""

import re
import uuid

import pytest
from httpx import AsyncClient, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.mail import Letter
from app.core.security import verify_password
from app.models import AuditLog, Session, User, UserRole
from app.services import notifications, sessions
from tests.integration.conftest import (
    act_as,
    answer_second_factor,
    csrf_headers,
    enrol_second_factor,
    login,
    register_buyer,
    seed_staff,
)

pytestmark = pytest.mark.integration

MODERATORS = "/api/v1/admin/moderators"
CHOSEN = "a-password-of-my-own-1"


def an_email() -> str:
    return f"moderator-{uuid.uuid4().hex}@example.com"


async def create(client: AsyncClient, email: str) -> Response:
    return await client.post(MODERATORS, json={"email": email}, headers=csrf_headers(client))


def handed_over(response: Response) -> str:
    """The generated password, readable in this one answer and nowhere afterwards."""
    password: str = response.json()["password"]
    return password


@pytest.fixture
def letters(monkeypatch: pytest.MonkeyPatch) -> list[Letter]:
    caught: list[Letter] = []

    def fake_deliver(settings: object, letter: Letter) -> None:
        caught.append(letter)

    monkeypatch.setattr(notifications, "deliver", fake_deliver)
    return caught


async def test_the_administrator_appoints_a_moderator(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    await act_as(api_client, await seed_staff(session, UserRole.ADMIN))
    email = an_email()

    response = await create(api_client, email)

    assert response.status_code == 201
    body = response.json()["user"]
    assert body["role"] == "moderator"
    assert body["email"] == email
    # handed over, therefore temporary
    assert body["must_change_password"] is True


async def test_the_address_is_normalized(api_client: AsyncClient, session: AsyncSession) -> None:
    await act_as(api_client, await seed_staff(session, UserRole.ADMIN))
    email = an_email()

    response = await create(api_client, f"  {email.upper()}  ")

    assert response.json()["user"]["email"] == email


async def test_the_address_is_told_a_staff_account_was_opened_on_it(
    api_client: AsyncClient, session: AsyncSession, letters: list[Letter]
) -> None:
    """The one reader who asked for nothing. Somebody else typed their address, and this is
    how they find out while the handed-over password is still unspent."""
    await act_as(api_client, await seed_staff(session, UserRole.ADMIN))
    email = an_email()

    await create(api_client, email)

    assert [letter.to for letter in letters] == [email]
    assert "модератора" in letters[0].body


async def test_the_handed_over_password_is_not_in_the_letter(
    api_client: AsyncClient, session: AsyncSession, letters: list[Letter]
) -> None:
    """A letter carrying it would make one readable mailbox enough to moderate with."""
    await act_as(api_client, await seed_staff(session, UserRole.ADMIN))

    created = await create(api_client, an_email())

    assert handed_over(created) not in letters[0].body


async def test_a_refused_appointment_writes_to_nobody(
    api_client: AsyncClient, session: AsyncSession, letters: list[Letter]
) -> None:
    """The address belongs to somebody already, and they are not becoming a moderator — a
    letter saying they were would be a letter about something that did not happen."""
    await register_buyer(api_client)
    await act_as(api_client, await seed_staff(session, UserRole.ADMIN))

    refused = await create(api_client, "buyer@example.com")

    assert refused.status_code == 409
    # the registration above wrote to them, and that is the only letter they should have
    assert [letter.subject for letter in letters] == ["Подтверждение адреса — AllStore.am"]


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
    password = handed_over(await create(api_client, email))

    api_client.cookies.clear()
    assert (await login(api_client, email, password)).status_code == 200
    refused = await api_client.get("/api/v1/moderation/products")

    assert refused.status_code == 403
    assert refused.json()["error"]["code"] == "password_change_required"


async def test_choosing_a_password_is_the_first_of_two_gates(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    """A moderator owes two things on the way in: a password that is their own, and a second
    factor. The queue opens after both, and the order is fixed — enrolling an authenticator
    against a password somebody else chose would be enrolling it for them."""
    await act_as(api_client, await seed_staff(session, UserRole.ADMIN))
    email = an_email()
    password = handed_over(await create(api_client, email))

    api_client.cookies.clear()
    await login(api_client, email, password)
    await api_client.post(
        "/api/v1/auth/password",
        json={"current_password": password, "password": CHOSEN},
        headers=csrf_headers(api_client),
    )
    api_client.cookies.clear()
    await login(api_client, email, CHOSEN)

    still_owing = await api_client.get("/api/v1/moderation/products")
    assert still_owing.status_code == 403
    assert still_owing.json()["error"]["code"] == "totp_setup_required"

    moderator = (await session.execute(select(User).where(User.email == email))).scalar_one()
    await enrol_second_factor(session, moderator)
    api_client.cookies.clear()
    await login(api_client, email, CHOSEN)
    await answer_second_factor(api_client, moderator)

    assert (await api_client.get("/api/v1/moderation/products")).status_code == 200


async def test_a_reset_tells_the_moderator_and_carries_no_password(
    api_client: AsyncClient, session: AsyncSession, letters: list[Letter]
) -> None:
    """Until this existed the old password simply stopped working, and its owner had no way
    to tell a reset they asked for from one they did not."""
    await act_as(api_client, await seed_staff(session, UserRole.ADMIN))
    email = an_email()
    appointed = (await create(api_client, email)).json()

    response = await api_client.post(
        f"{MODERATORS}/{appointed['user']['id']}/password", headers=csrf_headers(api_client)
    )

    reset_letter = letters[-1]
    assert reset_letter.to == email
    assert response.json()["password"] not in reset_letter.body
    assert appointed["password"] not in reset_letter.body


async def test_the_first_sign_in_is_told_to_both_people_who_knew_the_password(
    api_client: AsyncClient, session: AsyncSession, letters: list[Letter]
) -> None:
    """The handed-over password travels by hand, and that journey is the one part nobody can
    watch. A first sign-in its owner does not recognise is how being read on the way shows."""
    admin = await seed_staff(session, UserRole.ADMIN)
    await act_as(api_client, admin)
    email = an_email()
    password = handed_over(await create(api_client, email))
    letters.clear()

    api_client.cookies.clear()
    await login(api_client, email, password)

    assert {letter.to for letter in letters} == {email, admin.email}
    assert all(password not in letter.body for letter in letters)


async def test_the_second_sign_in_tells_nobody(
    api_client: AsyncClient, session: AsyncSession, letters: list[Letter]
) -> None:
    """A letter on each of somebody's own sign-ins is a letter they stop reading, and then
    the one that mattered goes unread too."""
    await act_as(api_client, await seed_staff(session, UserRole.ADMIN))
    email = an_email()
    password = handed_over(await create(api_client, email))
    api_client.cookies.clear()
    await login(api_client, email, password)
    letters.clear()

    api_client.cookies.clear()
    await login(api_client, email, password)

    assert [letter.subject for letter in letters] == ["Новый вход в аккаунт — AllStore.am"]


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
    appointed = (await create(api_client, email)).json()
    first = appointed["password"]

    response = await api_client.post(
        f"{MODERATORS}/{appointed['user']['id']}/password", headers=csrf_headers(api_client)
    )

    assert response.status_code == 200
    replacement = response.json()["password"]
    assert replacement != first
    user = (await session.execute(select(User).where(User.email == email))).scalars().one()
    await session.refresh(user)
    assert verify_password(replacement, user.password_hash)
    # handed over again, so it expires again
    assert user.must_change_password is True


async def test_the_replaced_password_ends_the_sessions_that_held_the_old_one(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    """The usual reason to reach this screen is that somebody else may be holding one. A
    session left alive would keep that somebody signed in under the password being replaced —
    the same rule every other credential change already follows."""
    await act_as(api_client, await seed_staff(session, UserRole.ADMIN))
    email = an_email()
    created = (await create(api_client, email)).json()["user"]
    moderator = (await session.execute(select(User).where(User.email == email))).scalars().one()
    await sessions.open_session(session, get_settings(), moderator)
    await session.commit()

    await api_client.post(
        f"{MODERATORS}/{created['id']}/password", headers=csrf_headers(api_client)
    )

    rows = (
        (await session.execute(select(Session).where(Session.user_id == moderator.id)))
        .scalars()
        .all()
    )
    assert rows
    assert all(row.revoked_at is not None for row in rows)


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


async def test_a_password_cannot_be_dictated_to_the_platform(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    """Weak ones were the reason for generating; accepting one anyway would make the change
    a suggestion. The schema forbids the field rather than ignoring it, so an administrator
    who sends one is told, instead of quietly getting a password they did not get."""
    await act_as(api_client, await seed_staff(session, UserRole.ADMIN))

    dictated = await api_client.post(
        MODERATORS,
        json={"email": an_email(), "password": "qwerty-123456"},
        headers=csrf_headers(api_client),
    )

    assert dictated.status_code == 422


async def test_no_two_appointments_hand_over_the_same_password(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    """One password used for every moderator is the other half of what generating fixes."""
    await act_as(api_client, await seed_staff(session, UserRole.ADMIN))

    first = handed_over(await create(api_client, an_email()))
    second = handed_over(await create(api_client, an_email()))

    assert first != second
    # four groups of four, and nothing in it that has to be guessed at when read aloud
    assert re.fullmatch(r"[a-z2-9]{4}(-[a-z2-9]{4}){3}", first)
