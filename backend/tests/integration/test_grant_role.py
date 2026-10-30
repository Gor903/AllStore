"""The break-glass path into a staff role, and what it does to the password.

A password typed on somebody's command line is known to whoever typed it. An account created
that way gets in once and then has to choose its own — the same rule as an administrator
bootstrapped from the environment. An account that already existed is not asked: nobody
handed it anything.
"""

import uuid

import pytest
from scripts.grant_role import apply
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password, verify_password
from app.models import AuditLog, User, UserRole

pytestmark = pytest.mark.integration

PASSWORD = "granted-password-1"
OWN_PASSWORD = "chosen-by-me-1"


def an_email() -> str:
    return f"granted-{uuid.uuid4().hex}@example.com"


async def found(session: AsyncSession, email: str) -> User:
    return (await session.execute(select(User).where(User.email == email))).scalars().one()


async def test_a_created_account_has_to_replace_the_password(session: AsyncSession) -> None:
    email = an_email()

    outcome = await apply(session, email, PASSWORD, UserRole.MODERATOR)
    await session.flush()

    assert "временный" in outcome.message
    user = await found(session, email)
    assert user.role is UserRole.MODERATOR
    assert user.must_change_password is True


async def test_promoting_an_existing_account_leaves_its_password_alone(
    session: AsyncSession,
) -> None:
    """They chose it themselves, long before anybody granted them a role."""
    email = an_email()
    session.add(User(email=email, password_hash=hash_password(OWN_PASSWORD), role=UserRole.BUYER))
    await session.flush()

    await apply(session, email, PASSWORD, UserRole.MODERATOR)
    await session.flush()

    user = await found(session, email)
    assert user.role is UserRole.MODERATOR
    assert user.must_change_password is False
    assert verify_password(OWN_PASSWORD, user.password_hash)


async def test_a_reset_hands_over_a_password_and_it_expires(session: AsyncSession) -> None:
    """The way back in for a moderator who lost theirs — and the way the end-to-end harness
    starts every run from the same place."""
    email = an_email()
    session.add(
        User(email=email, password_hash=hash_password(OWN_PASSWORD), role=UserRole.MODERATOR)
    )
    await session.flush()

    outcome = await apply(session, email, PASSWORD, UserRole.MODERATOR, reset_password=True)
    await session.flush()

    assert "временный" in outcome.message
    user = await found(session, email)
    assert verify_password(PASSWORD, user.password_hash)
    assert user.must_change_password is True


async def test_a_second_run_changes_nothing(session: AsyncSession) -> None:
    email = an_email()
    await apply(session, email, PASSWORD, UserRole.MODERATOR)
    await session.flush()

    outcome = await apply(session, email, "something-else-1", UserRole.MODERATOR)

    assert "ничего не менялось" in outcome.message
    assert verify_password(PASSWORD, (await found(session, email)).password_hash)


async def test_every_grant_leaves_a_record_with_nobody_in_the_actor(
    session: AsyncSession,
) -> None:
    """Authority handed out from a server shell answers to whoever holds the shell, so there
    is no actor to name — and that is precisely why it has to be written down. A moderator who
    appears with no entry is indistinguishable from one who was always there."""
    email = an_email()

    await apply(session, email, PASSWORD, UserRole.MODERATOR)
    await apply(session, email, PASSWORD, UserRole.SELLER)
    await apply(session, email, PASSWORD, UserRole.SELLER, reset_password=True)

    written = (await session.execute(select(AuditLog).order_by(AuditLog.created_at))).scalars()
    entries = list(written)
    assert [entry.action for entry in entries] == [
        "user.role_granted",
        "user.role_granted",
        "user.password_granted",
    ]
    assert all(entry.actor_user_id is None for entry in entries)
    assert entries[1].details["from"] == "moderator"


async def test_a_run_that_changes_nothing_writes_nothing(session: AsyncSession) -> None:
    """It is safe to re-run, and a journal of re-runs is not a journal."""
    email = an_email()
    await apply(session, email, PASSWORD, UserRole.MODERATOR)

    await apply(session, email, PASSWORD, UserRole.MODERATOR)

    written = (await session.execute(select(AuditLog))).scalars().all()
    assert len(written) == 1
