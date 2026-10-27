"""The only door to the moderator role.

What is asserted here is mostly what must *not* happen: no self-registration, no second use,
no use by anyone but the invitee, no secret readable from the database, and no error message
that tells an outsider which addresses have been invited.
"""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient, Response
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.core.security import generate_token, hash_token
from app.deps.rate_limit import INVITATION_ATTEMPT_LIMIT
from app.models import AuditLog, InvitationStatus, ModeratorInvitation, User, UserRole
from app.services import invitations
from app.services.invitations import InvalidInvitationError
from tests.integration.conftest import (
    act_as,
    anonymous,
    csrf_headers,
    register_buyer,
    seed_staff,
)

pytestmark = pytest.mark.integration

INVITATIONS = "/api/v1/admin/moderator-invitations"
REGISTER = "/api/v1/auth/register/moderator"
PASSWORD = "moderator-password-1"


def an_email() -> str:
    return f"invited-{uuid.uuid4().hex}@example.com"


async def invite(client: AsyncClient, email: str) -> Response:
    return await client.post(INVITATIONS, json={"email": email}, headers=csrf_headers(client))


async def accept(client: AsyncClient, token: str, email: str, **overrides: str) -> Response:
    body = {"token": token, "email": email, "password": PASSWORD, **overrides}
    client.cookies.clear()
    return await client.post(REGISTER, json=body)


async def as_admin(client: AsyncClient, session: AsyncSession) -> User:
    admin = await seed_staff(session, UserRole.ADMIN)
    await act_as(client, admin)
    return admin


async def an_invitation(
    client: AsyncClient, session: AsyncSession, email: str | None = None
) -> tuple[str, str, str]:
    """Returns the invitation id, the address it is for, and its one-time secret."""
    address = email or an_email()
    created = await invite(client, address)
    assert created.status_code == 201
    body = created.json()
    return str(body["invitation"]["id"]), address, str(body["token"])


async def stored(session: AsyncSession, invitation_id: str) -> ModeratorInvitation:
    found = await session.get(ModeratorInvitation, uuid.UUID(invitation_id))
    assert found is not None
    return found


async def test_an_administrator_invites_by_address(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    await as_admin(api_client, session)
    email = an_email()

    created = await invite(api_client, email)

    assert created.status_code == 201
    assert created.json()["invitation"]["email"] == email
    assert created.json()["invitation"]["status"] == "pending"
    assert created.json()["token"]


async def test_the_address_is_normalized(api_client: AsyncClient, session: AsyncSession) -> None:
    await as_admin(api_client, session)
    email = an_email()

    created = await invite(api_client, email.upper())

    assert created.json()["invitation"]["email"] == email


async def test_only_the_hash_of_the_secret_is_kept(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    """A database leak must not hand anybody a working invitation."""
    await as_admin(api_client, session)
    invitation_id, _, token = await an_invitation(api_client, session)

    row = await stored(session, invitation_id)

    assert row.token_hash == hash_token(token)
    assert token not in row.token_hash


@pytest.mark.parametrize("role", [UserRole.MODERATOR, UserRole.SELLER, UserRole.BUYER])
async def test_nobody_below_an_administrator_invites(
    api_client: AsyncClient, session: AsyncSession, role: UserRole
) -> None:
    """A moderator who could invite moderators would be an administrator under another name."""
    actor = await seed_staff(session, role)
    await act_as(api_client, actor)

    assert (await invite(api_client, an_email())).status_code == 403
    assert (await api_client.get(INVITATIONS)).status_code == 403


async def test_an_anonymous_visitor_invites_nobody(api_client: AsyncClient) -> None:
    await anonymous(api_client)

    assert (await api_client.get(INVITATIONS)).status_code == 401


async def test_inviting_without_the_csrf_header_is_forbidden(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    await as_admin(api_client, session)

    response = await api_client.post(INVITATIONS, json={"email": an_email()})

    assert response.status_code == 403


async def test_an_invitation_turns_the_invitee_into_a_moderator(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    await as_admin(api_client, session)
    _, email, token = await an_invitation(api_client, session)

    response = await accept(api_client, token, email)

    assert response.status_code == 201
    assert response.json()["role"] == "moderator"
    assert response.json()["email"] == email


async def test_the_new_moderator_is_signed_in_and_sees_the_queue(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    await as_admin(api_client, session)
    _, email, token = await an_invitation(api_client, session)

    await accept(api_client, token, email)

    assert (await api_client.get("/api/v1/moderation/products")).status_code == 200


async def test_nobody_registers_as_a_moderator_without_an_invitation(
    api_client: AsyncClient,
) -> None:
    await anonymous(api_client)

    response = await accept(api_client, "not-a-real-token", an_email())

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_invitation"


async def test_the_role_is_not_a_field_anyone_may_ask_for(api_client: AsyncClient) -> None:
    """The ordinary registration forms take no role, and asking for one is refused outright
    rather than quietly ignored."""
    await anonymous(api_client)

    response = await api_client.post(
        "/api/v1/auth/register/buyer",
        json={"email": an_email(), "password": PASSWORD, "role": "moderator"},
    )

    assert response.status_code == 201
    assert response.json()["role"] == "buyer"


async def test_a_link_forwarded_to_somebody_else_stops_working(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    await as_admin(api_client, session)
    invitation_id, _, token = await an_invitation(api_client, session)

    response = await accept(api_client, token, an_email())

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_invitation"
    # the invitation is spent all the same: whoever holds the link had their one attempt
    assert (await stored(session, invitation_id)).used_at is not None


async def test_an_invitation_is_spent_once(api_client: AsyncClient, session: AsyncSession) -> None:
    await as_admin(api_client, session)
    _, email, token = await an_invitation(api_client, session)
    await accept(api_client, token, email)

    second = await accept(api_client, token, email)

    assert second.status_code == 422
    moderators = await session.execute(select(User).where(User.email == email))
    assert len(moderators.scalars().all()) == 1


async def test_an_expired_invitation_is_refused(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    await as_admin(api_client, session)
    invitation_id, email, token = await an_invitation(api_client, session)
    row = await stored(session, invitation_id)
    row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    await session.flush()

    response = await accept(api_client, token, email)

    assert response.status_code == 422
    assert (await stored(session, invitation_id)).status is InvitationStatus.EXPIRED


async def test_a_revoked_invitation_is_refused(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    await as_admin(api_client, session)
    invitation_id, email, token = await an_invitation(api_client, session)
    revoked = await api_client.post(
        f"{INVITATIONS}/{invitation_id}/revoke", headers=csrf_headers(api_client)
    )
    assert revoked.status_code == 200

    response = await accept(api_client, token, email)

    assert response.status_code == 422
    assert (await stored(session, invitation_id)).status is InvitationStatus.REVOKED


async def test_every_refusal_says_the_same_thing(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    """Otherwise the form answers questions nobody asked: who has been invited, whose link
    has already been used, which addresses exist at all."""
    await as_admin(api_client, session)
    invitation_id, email, token = await an_invitation(api_client, session)
    await api_client.post(f"{INVITATIONS}/{invitation_id}/revoke", headers=csrf_headers(api_client))

    unknown = await accept(api_client, "not-a-real-token", an_email())
    revoked = await accept(api_client, token, email)
    wrong_address = await accept(api_client, token, an_email())

    answers = {unknown.json()["error"]["message"] for _ in [0]}
    answers |= {revoked.json()["error"]["message"], wrong_address.json()["error"]["message"]}
    assert len(answers) == 1
    assert {unknown.status_code, revoked.status_code, wrong_address.status_code} == {422}


async def test_a_second_live_invitation_for_one_address_is_refused(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    """Two working links for one person is two answers to "which one is valid"."""
    await as_admin(api_client, session)
    _, email, _ = await an_invitation(api_client, session)

    response = await invite(api_client, email)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "invitation_already_open"


async def test_revoking_frees_the_address_for_a_new_invitation(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    await as_admin(api_client, session)
    invitation_id, email, _ = await an_invitation(api_client, session)
    await api_client.post(f"{INVITATIONS}/{invitation_id}/revoke", headers=csrf_headers(api_client))

    response = await invite(api_client, email)

    assert response.status_code == 201


async def test_the_old_link_does_not_come_back_with_the_new_one(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    await as_admin(api_client, session)
    first_id, email, first_token = await an_invitation(api_client, session)
    await api_client.post(f"{INVITATIONS}/{first_id}/revoke", headers=csrf_headers(api_client))
    _, _, second_token = await an_invitation(api_client, session, email)

    assert (await accept(api_client, first_token, email)).status_code == 422
    await act_as(api_client, await seed_staff(session, UserRole.MODERATOR))
    assert (await accept(api_client, second_token, email)).status_code == 201


async def test_an_address_that_already_has_an_account_is_not_invited(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    """There is a screen for that: changing the role of an account that exists."""
    await anonymous(api_client)
    email = an_email()
    await register_buyer(api_client, email=email)
    await as_admin(api_client, session)

    response = await invite(api_client, email)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "account_exists"


async def test_only_a_live_invitation_is_revoked(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    admin = await as_admin(api_client, session)
    invitation_id, email, token = await an_invitation(api_client, session)
    await accept(api_client, token, email)
    # the accepted invitation signed the new moderator in, so the administrator logs back in
    await act_as(api_client, admin)

    response = await api_client.post(
        f"{INVITATIONS}/{invitation_id}/revoke", headers=csrf_headers(api_client)
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "invitation_not_pending"


async def test_revoking_something_that_is_not_there_answers_404(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    await as_admin(api_client, session)

    response = await api_client.post(
        f"{INVITATIONS}/{uuid.uuid4()}/revoke", headers=csrf_headers(api_client)
    )

    assert response.status_code == 404


async def test_the_list_shows_what_became_of_each_invitation(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    admin = await as_admin(api_client, session)
    _, accepted_email, accepted_token = await an_invitation(api_client, session)
    revoked_id, _, _ = await an_invitation(api_client, session)
    await an_invitation(api_client, session)
    await api_client.post(f"{INVITATIONS}/{revoked_id}/revoke", headers=csrf_headers(api_client))
    await accept(api_client, accepted_token, accepted_email)
    await act_as(api_client, admin)

    body = (await api_client.get(INVITATIONS)).json()

    assert body["total"] == 3
    # newest first
    assert [item["status"] for item in body["items"]] == ["pending", "revoked", "accepted"]
    assert all(item["created_by_email"] == admin.email for item in body["items"])
    assert all("token" not in item for item in body["items"])


async def test_the_list_never_shows_a_secret(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    await as_admin(api_client, session)
    _, _, token = await an_invitation(api_client, session)

    body = (await api_client.get(INVITATIONS)).text

    assert token not in body


async def test_the_whole_life_of_an_invitation_is_journalled(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    admin = await as_admin(api_client, session)
    _, email, token = await an_invitation(api_client, session)
    second_id, _, _ = await an_invitation(api_client, session)
    await api_client.post(f"{INVITATIONS}/{second_id}/revoke", headers=csrf_headers(api_client))
    await accept(api_client, token, email)

    written = (
        (await session.execute(select(AuditLog).order_by(AuditLog.created_at))).scalars().all()
    )
    assert [entry.action for entry in written] == [
        "moderator.invited",
        "moderator.invited",
        "moderator.invite_revoked",
        "moderator.invite_accepted",
    ]
    assert written[0].actor_user_id == admin.id
    assert written[0].details == {"email": email}


async def test_the_journal_never_carries_the_secret(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    await as_admin(api_client, session)
    _, _, token = await an_invitation(api_client, session)

    written = (await session.execute(select(AuditLog))).scalars().all()

    assert all(token not in str(entry.details) for entry in written)


async def test_guessing_is_cut_off_after_a_handful_of_attempts(
    api_client: AsyncClient,
) -> None:
    """The secret is 32 random bytes and unguessable in any number of tries this allows; the
    limit is here so a flood costs the attacker rather than the password hasher."""
    await anonymous(api_client)

    answers = [
        (await accept(api_client, f"guess-{attempt}", an_email())).status_code
        for attempt in range(INVITATION_ATTEMPT_LIMIT + 1)
    ]

    assert answers[:INVITATION_ATTEMPT_LIMIT] == [422] * INVITATION_ATTEMPT_LIMIT
    assert answers[-1] == 429


async def _accept_committed(engine: AsyncEngine, token: str, email: str) -> str | None:
    """The outcome of one of two racing registrations: the new account's id, or nothing."""
    # expire_on_commit=False: the identifier is read after the commit, and an expired
    # attribute would send the ORM back to the database outside its greenlet
    async with AsyncSession(engine, expire_on_commit=False) as session:
        try:
            user = await invitations.accept(session, token, email, PASSWORD)
            await session.commit()
        except (InvalidInvitationError, IntegrityError):
            await session.rollback()
            return None
        return str(user.id)


async def test_two_people_clicking_the_same_link_make_one_moderator(
    db_engine: AsyncEngine,
) -> None:
    """The real race, on two connections.

    A check-then-create would let both through: both read `used_at IS NULL`, both go on to
    make an account. The claim is a single UPDATE instead, so the second request finds the
    row already spent and has nothing to build on.
    """
    email = an_email()
    token = generate_token()
    invitation_id = uuid.uuid4()
    async with AsyncSession(db_engine) as setup:
        setup.add(
            ModeratorInvitation(
                id=invitation_id,
                email=email,
                token_hash=hash_token(token),
                expires_at=datetime.now(UTC) + timedelta(hours=1),
            )
        )
        await setup.commit()

    try:
        outcomes = await asyncio.gather(
            _accept_committed(db_engine, token, email),
            _accept_committed(db_engine, token, email),
        )

        assert len([outcome for outcome in outcomes if outcome is not None]) == 1
        async with AsyncSession(db_engine) as check:
            made = await check.execute(select(User).where(User.email == email))
            assert len(made.scalars().all()) == 1
    finally:
        async with AsyncSession(db_engine) as cleanup:
            # the journal entry too: it survives the account it names, by design, so a test
            # that committed one has to take it back or it haunts every later assertion
            await cleanup.execute(delete(AuditLog).where(AuditLog.entity_id == invitation_id))
            await cleanup.execute(
                delete(ModeratorInvitation).where(ModeratorInvitation.email == email)
            )
            await cleanup.execute(delete(User).where(User.email == email))
            await cleanup.commit()
