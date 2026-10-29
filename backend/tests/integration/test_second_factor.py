"""A password is one thing somebody knows, and for staff it stops being enough.

The rules worth proving are the ones that make the factor a factor rather than a formality:
an enrolment nobody finished does not lock anybody out, a code works once, a staff account
without one cannot do anything but set one up, and a telephone at the bottom of a lake is not
the end of the account.
"""

import time
import uuid
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.mail import Letter
from app.core.totp import code_for, step_at
from app.models import AuditLog, TotpCredential, User, UserRole
from app.repositories import totp as totp_repo
from app.services import notifications
from tests.integration.conftest import (
    STAFF_PASSWORD,
    act_as,
    answer_second_factor,
    code_now,
    csrf_headers,
    login,
    register_buyer,
    seed_staff,
)

pytestmark = pytest.mark.integration

SETUP = "/api/v1/auth/totp/setup"
CONFIRM = "/api/v1/auth/totp/confirm"
DISABLE = "/api/v1/auth/totp/disable"
FINISH = "/api/v1/auth/login/totp"
STATUS = "/api/v1/auth/totp"
QUEUE = "/api/v1/moderation/products"


@pytest.fixture
def letters(monkeypatch: pytest.MonkeyPatch) -> list[Letter]:
    caught: list[Letter] = []

    def fake_deliver(settings: object, letter: Letter) -> None:
        caught.append(letter)

    monkeypatch.setattr(notifications, "deliver", fake_deliver)
    return caught


async def _enrol_through_the_screens(client: AsyncClient) -> tuple[str, list[str]]:
    """Walks the setup the way the interface does, and returns the secret and the codes."""
    started = await client.post(SETUP, headers=csrf_headers(client))
    assert started.status_code == 200
    secret = started.json()["secret"]
    confirmed = await client.post(
        CONFIRM, json={"code": code_for(secret, step_at(time.time()))}, headers=csrf_headers(client)
    )
    assert confirmed.status_code == 200
    return secret, list(confirmed.json()["recovery_codes"])


async def test_a_moderator_without_one_cannot_do_their_job(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    """The gate, and the whole point of it: the account that can bar people is the account
    that has to prove more than a password."""
    moderator = await seed_staff(session, UserRole.MODERATOR, second_factor=False)
    await act_as(api_client, moderator)

    refused = await api_client.get(QUEUE)

    assert refused.status_code == 403
    assert refused.json()["error"]["code"] == "totp_setup_required"


async def test_but_can_reach_the_screen_that_sets_one_up(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    """Otherwise the requirement would be a locked room with the key inside."""
    moderator = await seed_staff(session, UserRole.MODERATOR, second_factor=False)
    await act_as(api_client, moderator)

    assert (await api_client.get(STATUS)).status_code == 200
    assert (await api_client.post(SETUP, headers=csrf_headers(api_client))).status_code == 200


async def test_setting_one_up_opens_the_job(
    api_client: AsyncClient, session: AsyncSession, letters: list[Letter]
) -> None:
    moderator = await seed_staff(session, UserRole.MODERATOR, second_factor=False)
    await act_as(api_client, moderator)

    await _enrol_through_the_screens(api_client)

    assert (await api_client.get(QUEUE)).status_code == 200
    assert "Вход по коду изменён — AllStore.am" in [letter.subject for letter in letters]


async def test_a_buyer_may_have_one_without_being_asked_to(
    api_client: AsyncClient,
) -> None:
    """The requirement is narrow on purpose — one imposed on buyers is one they route around
    by not registering — but the door is open to anybody who wants it."""
    await register_buyer(api_client)

    _, codes = await _enrol_through_the_screens(api_client)

    assert len(codes) == 10
    assert (await api_client.get(STATUS)).json() == {
        "enabled": True,
        "required": False,
        "recovery_codes_left": 10,
    }


async def test_an_unfinished_enrolment_locks_nobody_out(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    """A secret written on our side that never reached a telephone would otherwise be an
    account behind an authenticator that does not exist."""
    moderator = await seed_staff(session, UserRole.MODERATOR, second_factor=False)
    await act_as(api_client, moderator)
    await api_client.post(SETUP, headers=csrf_headers(api_client))

    assert await totp_repo.credential_of(session, moderator.id) is not None
    assert not await totp_repo.is_in_force(session, moderator.id)
    # and the sign-in does not stop to ask for a code it could not answer
    api_client.cookies.clear()
    assert (await login(api_client, moderator.email, STAFF_PASSWORD)).status_code == 200


async def test_coming_back_to_the_screen_hands_out_a_new_secret(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    """Somebody who returns here has almost certainly lost the half-scanned code, and the old
    secret is the one thing they cannot use."""
    moderator = await seed_staff(session, UserRole.MODERATOR, second_factor=False)
    await act_as(api_client, moderator)
    first = (await api_client.post(SETUP, headers=csrf_headers(api_client))).json()["secret"]

    second = (await api_client.post(SETUP, headers=csrf_headers(api_client))).json()["secret"]

    assert first != second


async def test_the_password_alone_no_longer_opens_a_session(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    settings = get_settings()
    moderator = await seed_staff(session, UserRole.MODERATOR)
    api_client.cookies.clear()

    paused = await login(api_client, moderator.email, STAFF_PASSWORD)

    assert paused.status_code == 401
    assert paused.json()["error"]["code"] == "totp_required"
    assert settings.session_cookie not in api_client.cookies
    # and the note saying who got this far is there, or the second half would have nobody
    assert "allstore_totp" in api_client.cookies


async def test_the_code_finishes_what_the_password_started(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    moderator = await seed_staff(session, UserRole.MODERATOR)
    api_client.cookies.clear()
    await login(api_client, moderator.email, STAFF_PASSWORD)

    finished = await answer_second_factor(api_client, moderator)

    assert finished.status_code == 200
    assert (await api_client.get(QUEUE)).status_code == 200


async def test_a_code_works_once(api_client: AsyncClient, session: AsyncSession) -> None:
    """It is valid for its step and the drift either side, so without this a code read over
    somebody's shoulder works a second time."""
    moderator = await seed_staff(session, UserRole.MODERATOR)
    api_client.cookies.clear()
    await login(api_client, moderator.email, STAFF_PASSWORD)
    code = code_now(moderator)
    assert (await api_client.post(FINISH, json={"code": code})).status_code == 200

    api_client.cookies.clear()
    await login(api_client, moderator.email, STAFF_PASSWORD)
    again = await api_client.post(FINISH, json={"code": code})

    assert again.status_code == 403


async def test_a_wrong_code_does_not_open_anything(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    settings = get_settings()
    moderator = await seed_staff(session, UserRole.MODERATOR)
    api_client.cookies.clear()
    await login(api_client, moderator.email, STAFF_PASSWORD)

    refused = await api_client.post(FINISH, json={"code": "000000"})

    assert refused.status_code == 403
    assert settings.session_cookie not in api_client.cookies


async def test_a_code_with_no_sign_in_behind_it_is_refused(api_client: AsyncClient) -> None:
    """Without the note, a code is six digits anybody can type."""
    api_client.cookies.clear()

    refused = await api_client.post(FINISH, json={"code": "123456"})

    assert refused.status_code == 401


async def test_a_forged_note_is_refused(api_client: AsyncClient, session: AsyncSession) -> None:
    """A cookie the caller can write is a cookie the caller can use to claim they are halfway
    into somebody else's account."""
    moderator = await seed_staff(session, UserRole.MODERATOR)
    api_client.cookies.clear()
    api_client.cookies.set("allstore_totp", f"deadbeef.{moderator.id}")

    refused = await api_client.post(FINISH, json={"code": code_now(moderator)})

    assert refused.status_code == 401


async def test_a_recovery_code_gets_somebody_in_and_is_then_spent(
    api_client: AsyncClient, letters: list[Letter]
) -> None:
    """A telephone at the bottom of a lake is not the end of the account — and it is the end
    of that particular code."""
    await register_buyer(api_client)
    _, codes = await _enrol_through_the_screens(api_client)
    api_client.cookies.clear()
    letters.clear()
    await login(api_client, "buyer@example.com", "buyer-password-1")

    opened = await api_client.post(FINISH, json={"code": codes[0]})

    assert opened.status_code == 200
    assert "Использован резервный код — AllStore.am" in [letter.subject for letter in letters]

    api_client.cookies.clear()
    await login(api_client, "buyer@example.com", "buyer-password-1")
    assert (await api_client.post(FINISH, json={"code": codes[0]})).status_code == 403


async def test_turning_it_off_asks_for_a_code(api_client: AsyncClient) -> None:
    """An unattended screen reaches this; it must not be enough to take the factor off."""
    await register_buyer(api_client)
    await _enrol_through_the_screens(api_client)

    refused = await api_client.post(
        DISABLE, json={"code": "000000"}, headers=csrf_headers(api_client)
    )

    assert refused.status_code == 403
    assert (await api_client.get(STATUS)).json()["enabled"] is True


async def test_turning_it_off_works_with_one(
    api_client: AsyncClient, letters: list[Letter]
) -> None:
    await register_buyer(api_client)
    secret, _ = await _enrol_through_the_screens(api_client)
    letters.clear()

    # a step ahead: the code that confirmed the enrolment has already been spent
    gone = await api_client.post(
        DISABLE,
        json={"code": code_for(secret, step_at(time.time()) + 1)},
        headers=csrf_headers(api_client),
    )

    assert gone.status_code == 204
    assert (await api_client.get(STATUS)).json()["enabled"] is False
    assert "выключен" in letters[0].body


async def test_both_directions_reach_the_journal(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    await register_buyer(api_client)
    secret, _ = await _enrol_through_the_screens(api_client)
    await api_client.post(
        DISABLE,
        json={"code": code_for(secret, step_at(time.time()) + 1)},
        headers=csrf_headers(api_client),
    )

    actions = [
        entry.action
        for entry in (await session.execute(select(AuditLog).order_by(AuditLog.created_at)))
        .scalars()
        .all()
    ]
    assert actions == ["user.totp_enabled", "user.totp_disabled"]


async def test_the_secret_is_not_in_the_table_as_it_was_given_out(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    """A dump of this table is a copy of every second factor on the platform unless the
    column is encrypted."""
    await register_buyer(api_client)
    secret, _ = await _enrol_through_the_screens(api_client)

    stored = (await session.execute(select(TotpCredential))).scalars().one()

    assert secret not in stored.secret_encrypted


async def test_an_account_that_cannot_be_decrypted_refuses_rather_than_opens(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    """The key changed or the row was altered. Either way the answer is no, not yes."""
    moderator = await seed_staff(session, UserRole.MODERATOR)
    row = await totp_repo.credential_of(session, moderator.id)
    assert row is not None
    row.secret_encrypted = "not-something-this-key-wrote"
    await session.flush()
    api_client.cookies.clear()
    await login(api_client, moderator.email, STAFF_PASSWORD)

    refused = await api_client.post(FINISH, json={"code": "123456"})

    assert refused.status_code == 403


async def test_a_blocked_account_does_not_get_in_on_a_correct_code(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    """The code is the second question. Whether the account may act at all is still the first."""
    from app.models import UserStatus

    moderator = await seed_staff(session, UserRole.MODERATOR)
    api_client.cookies.clear()
    await login(api_client, moderator.email, STAFF_PASSWORD)
    moderator.status = UserStatus.BLOCKED
    await session.flush()

    refused = await api_client.post(FINISH, json={"code": code_now(moderator)})

    assert refused.status_code == 403


async def test_a_note_that_went_stale_is_refused(
    api_client: AsyncClient, session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A stolen password plus this cookie is the account, so it must not sit in a browser."""
    from app.core import half_sign_in, sealed

    moderator = await seed_staff(session, UserRole.MODERATOR)
    api_client.cookies.clear()
    api_client.cookies.set(
        half_sign_in.COOKIE,
        sealed.seal(
            get_settings(),
            {"user": str(moderator.id)},
            now=datetime.now(UTC).timestamp() - half_sign_in.TTL_SECONDS - 1,
        ),
    )

    refused = await api_client.post(FINISH, json={"code": code_now(moderator)})

    assert refused.status_code == 401


async def test_signing_in_somewhere_new_is_still_reported(
    api_client: AsyncClient, session: AsyncSession, letters: list[Letter]
) -> None:
    """The letter is sent by the half that opens the session, which is no longer the one that
    takes the password — easy to lose in the move, and it is the letter that catches a theft."""
    moderator = await seed_staff(session, UserRole.MODERATOR)
    await act_as(api_client, moderator)
    api_client.cookies.clear()
    letters.clear()

    await login(api_client, moderator.email, STAFF_PASSWORD)
    await answer_second_factor(api_client, moderator)

    assert "Новый вход в аккаунт — AllStore.am" in [letter.subject for letter in letters]


async def test_break_glass_takes_the_factor_away_with_the_password(
    session: AsyncSession,
) -> None:
    """An administrator who lost the telephone and the codes would otherwise have locked the
    one administrator seat the platform allows, with no screen anywhere that undoes it."""
    from scripts.grant_role import apply

    moderator = await seed_staff(session, UserRole.MODERATOR)
    assert await totp_repo.is_in_force(session, moderator.id)

    await apply(session, moderator.email, "handed-over-1", UserRole.MODERATOR, reset_password=True)

    assert not await totp_repo.is_in_force(session, moderator.id)
    actions = {entry.action for entry in (await session.execute(select(AuditLog))).scalars().all()}
    assert "user.totp_revoked" in actions


async def test_enrolling_waits_for_the_password_to_be_their_own(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    """Enrolling an authenticator against a password somebody else chose would be enrolling
    it for them."""
    moderator = await seed_staff(session, UserRole.MODERATOR, second_factor=False)
    moderator.must_change_password = True
    await session.flush()
    await act_as(api_client, moderator)

    refused = await api_client.post(SETUP, headers=csrf_headers(api_client))

    assert refused.status_code == 403
    assert refused.json()["error"]["code"] == "password_change_required"


async def test_the_enrolment_belongs_to_one_account(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    """One per account: two is two to keep track of, and the unique index is what says so."""
    await register_buyer(api_client)
    await _enrol_through_the_screens(api_client)
    owner = (await session.execute(select(User))).scalars().one()

    rows = (
        await session.execute(select(TotpCredential).where(TotpCredential.user_id == owner.id))
    ).scalars()

    assert len(list(rows)) == 1


async def test_starting_again_while_enrolled_is_refused(api_client: AsyncClient) -> None:
    """Replacing it silently would leave somebody holding an authenticator that no longer
    opens anything, and no way to tell."""
    await register_buyer(api_client)
    await _enrol_through_the_screens(api_client)

    refused = await api_client.post(SETUP, headers=csrf_headers(api_client))

    assert refused.status_code == 409
    assert refused.json()["error"]["code"] == "totp_already_enrolled"


async def test_somebody_elses_recovery_code_is_nobody_s_way_in(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    await register_buyer(api_client, email="first@example.com")
    _, codes = await _enrol_through_the_screens(api_client)
    api_client.cookies.clear()
    stranger = await seed_staff(session, UserRole.MODERATOR)
    await login(api_client, stranger.email, STAFF_PASSWORD)

    refused = await api_client.post(FINISH, json={"code": codes[0]})

    assert refused.status_code == 403


async def test_an_unknown_account_in_the_note_is_refused(api_client: AsyncClient) -> None:
    from app.core import half_sign_in, sealed

    api_client.cookies.clear()
    api_client.cookies.set(
        half_sign_in.COOKIE, sealed.seal(get_settings(), {"user": str(uuid.uuid4())})
    )

    refused = await api_client.post(FINISH, json={"code": "123456"})

    assert refused.status_code in (401, 403)
