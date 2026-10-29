"""The first administrator: created once, from the environment, and never twice.

Most of this suite runs inside a transaction that is rolled back. Two of these tests cannot —
a race needs two connections, and two connections only see each other's work once it is
committed. Those tests clean up after themselves in a `finally`, because a committed
administrator left behind would make every later test that seeds one fail against the unique
index, and the failure would point anywhere but here.
"""

import asyncio
import uuid

import pytest
from pydantic import SecretStr
from sqlalchemy import delete, func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.core.config import get_settings
from app.core.security import hash_password, verify_password
from app.models import AccountBlock, User, UserRole, UserStatus
from app.services.admin_bootstrap import (
    BootstrapNotConfiguredError,
    Outcome,
    bootstrap,
    bootstrap_on_startup,
)
from app.services.auth import password_of

pytestmark = pytest.mark.integration

PASSWORD = "bootstrap-password-1"
OTHER_PASSWORD = "bootstrap-password-2"


def an_email() -> str:
    return f"admin-{uuid.uuid4().hex}@example.com"


async def admins(session: AsyncSession) -> list[User]:
    result = await session.execute(select(User).where(User.role == UserRole.ADMIN))
    return list(result.scalars().all())


async def test_the_first_run_creates_the_administrator(session: AsyncSession) -> None:
    email = an_email()

    result = await bootstrap(session, email, PASSWORD)

    assert result.outcome is Outcome.CREATED
    created = await admins(session)
    assert [user.email for user in created] == [email]
    assert created[0].status is UserStatus.ACTIVE


async def test_the_address_is_normalized(session: AsyncSession) -> None:
    """Addresses differing only in case are one account everywhere else; here too."""
    email = an_email()

    await bootstrap(session, f"  {email.upper()}  ", PASSWORD)

    assert [user.email for user in await admins(session)] == [email]


async def test_a_second_run_changes_nothing(session: AsyncSession) -> None:
    email = an_email()
    await bootstrap(session, email, PASSWORD)

    result = await bootstrap(session, email, PASSWORD)

    assert result.outcome is Outcome.UNCHANGED
    assert len(await admins(session)) == 1


async def test_a_second_run_does_not_rewrite_the_password(session: AsyncSession) -> None:
    """Redeploying with a stale ADMIN_PASSWORD in the environment must not hand the account
    back to whoever last edited that file."""
    email = an_email()
    await bootstrap(session, email, PASSWORD)

    await bootstrap(session, email, OTHER_PASSWORD)

    admin = (await admins(session))[0]
    assert verify_password(PASSWORD, password_of(admin))
    assert not verify_password(OTHER_PASSWORD, password_of(admin))


async def test_a_second_run_under_another_address_changes_nothing(
    session: AsyncSession,
) -> None:
    """The environment is configuration, not a register: once there is an administrator, the
    database is the authority on who it is."""
    first = an_email()
    await bootstrap(session, first, PASSWORD)

    result = await bootstrap(session, an_email(), PASSWORD)

    assert result.outcome is Outcome.UNCHANGED
    assert [user.email for user in await admins(session)] == [first]


async def test_startup_without_configuration_does_nothing_and_says_nothing(
    session: AsyncSession,
) -> None:
    """A stand with no ADMIN_EMAIL wants no administrator; that is not a misconfiguration."""
    settings = get_settings().model_copy(update={"admin_email": None, "admin_password": None})

    assert await bootstrap_on_startup(session, settings) is None
    assert await admins(session) == []


async def test_startup_creates_the_administrator_the_environment_names(
    db_engine: AsyncEngine,
) -> None:
    """Committed on purpose — the application does commit — so this one cleans up after itself."""
    email = an_email()
    settings = get_settings().model_copy(
        update={"admin_email": email, "admin_password": SecretStr(PASSWORD)}
    )
    async with AsyncSession(db_engine) as session:
        try:
            first = await bootstrap_on_startup(session, settings)
            # the second start of the same deploy must be a no-op, not a second administrator
            second = await bootstrap_on_startup(session, settings)

            assert "создан" in str(first)
            assert "ничего не менялось" in str(second)
            assert len(await admins(session)) == 1
        finally:
            await session.execute(delete(User).where(User.email == email))
            await session.commit()


async def test_the_created_administrator_has_to_choose_their_own_password(
    session: AsyncSession,
) -> None:
    """The password came from a deploy variable, which is as good as written on a wall."""
    email = an_email()

    await bootstrap(session, email, PASSWORD)

    assert (await admins(session))[0].must_change_password is True


async def test_an_existing_account_is_promoted_and_keeps_its_password(
    session: AsyncSession,
) -> None:
    email = an_email()
    session.add(User(email=email, password_hash=hash_password(PASSWORD), role=UserRole.BUYER))
    await session.flush()

    result = await bootstrap(session, email, OTHER_PASSWORD)

    assert result.outcome is Outcome.PROMOTED
    admin = (await admins(session))[0]
    assert admin.email == email
    assert verify_password(PASSWORD, password_of(admin))
    # nobody handed them this password: it is the one they registered with
    assert admin.must_change_password is False


async def test_promoting_a_barred_account_ends_the_ban_rather_than_hiding_it(
    session: AsyncSession,
) -> None:
    """Clearing the status alone would leave a row saying the person is barred beside a
    column saying they are not."""
    email = an_email()
    user = User(
        email=email,
        password_hash=hash_password(PASSWORD),
        role=UserRole.BUYER,
        status=UserStatus.BLOCKED,
    )
    session.add(user)
    await session.flush()
    session.add(AccountBlock(user_id=user.id, reason="Старая блокировка"))
    await session.flush()

    await bootstrap(session, email, PASSWORD)

    assert user.status is UserStatus.ACTIVE
    block = (await session.execute(select(AccountBlock))).scalars().one()
    assert block.revoked_at is not None


async def test_the_password_is_replaced_only_when_asked_for(session: AsyncSession) -> None:
    email = an_email()
    await bootstrap(session, email, PASSWORD)

    result = await bootstrap(session, email, OTHER_PASSWORD, reset_password=True)

    assert result.outcome is Outcome.PASSWORD_RESET
    admin = (await admins(session))[0]
    assert verify_password(OTHER_PASSWORD, password_of(admin))
    # recovery hands out a password the same way the first run does, so it expires the same way
    assert admin.must_change_password is True


async def test_the_recovery_run_lets_a_locked_out_administrator_back_in(
    session: AsyncSession,
) -> None:
    email = an_email()
    await bootstrap(session, email, PASSWORD)
    admin = (await admins(session))[0]
    admin.status = UserStatus.BLOCKED
    await session.flush()

    await bootstrap(session, email, OTHER_PASSWORD, reset_password=True)

    assert admin.status is UserStatus.ACTIVE


@pytest.mark.parametrize(
    ("email", "password"),
    [(None, PASSWORD), ("admin@example.com", None), (None, None), ("", PASSWORD)],
)
async def test_an_unconfigured_bootstrap_refuses_to_guess(
    session: AsyncSession, email: str | None, password: str | None
) -> None:
    with pytest.raises(BootstrapNotConfiguredError):
        await bootstrap(session, email, password)


async def test_the_message_never_carries_the_password(session: AsyncSession) -> None:
    """What this prints lands in deploy logs, and a deploy log is not a secret store."""
    email = an_email()

    created = await bootstrap(session, email, PASSWORD)
    reset = await bootstrap(session, email, PASSWORD, reset_password=True)

    assert PASSWORD not in created.message
    assert PASSWORD not in reset.message
    assert email in created.message


async def test_the_database_refuses_a_second_administrator(session: AsyncSession) -> None:
    """Every other guard is a check in Python, and two requests can pass the same check in the
    same moment. This one cannot be raced."""
    await bootstrap(session, an_email(), PASSWORD)

    session.add(User(email=an_email(), password_hash=hash_password(PASSWORD), role=UserRole.ADMIN))
    with pytest.raises(IntegrityError):
        await session.flush()


async def _bootstrap_committed(engine: AsyncEngine, email: str) -> Outcome:
    async with AsyncSession(engine) as session:
        result = await bootstrap(session, email, PASSWORD)
        await session.commit()
        return result.outcome


async def _forget_administrators(engine: AsyncEngine) -> None:
    async with AsyncSession(engine) as session:
        await session.execute(delete(User).where(User.role == UserRole.ADMIN))
        await session.commit()


async def test_two_bootstraps_at_once_leave_one_administrator(db_engine: AsyncEngine) -> None:
    """The real race, on two connections: the advisory lock queues them and the second one
    reads what the first wrote instead of colliding with it."""
    email = an_email()
    try:
        outcomes = await asyncio.gather(
            _bootstrap_committed(db_engine, email),
            _bootstrap_committed(db_engine, email),
        )

        assert sorted(outcomes) == [Outcome.CREATED, Outcome.UNCHANGED]
        async with AsyncSession(db_engine) as session:
            total = await session.execute(
                select(func.count()).select_from(User).where(User.role == UserRole.ADMIN)
            )
            assert total.scalar_one() == 1
    finally:
        await _forget_administrators(db_engine)


async def test_the_lock_is_what_makes_the_second_run_wait(db_engine: AsyncEngine) -> None:
    """Without the queue the second bootstrap would read an empty table and try to insert.

    The lock is held by the first transaction here, so the second one cannot get past it until
    the first commits — which is exactly what keeps the outcome a sentence rather than a
    unique-violation traceback.
    """
    email = an_email()
    try:
        async with AsyncSession(db_engine) as holder:
            await bootstrap(holder, email, PASSWORD)

            async with AsyncSession(db_engine) as waiting:
                blocked = asyncio.create_task(bootstrap(waiting, email, PASSWORD))
                # enough turns for the task to reach the lock and stop there
                for _ in range(10):
                    await asyncio.sleep(0)
                assert not blocked.done()

                await holder.commit()
                # a timeout rather than an open wait: a lock that is never released would
                # otherwise hang the suite instead of failing this test
                result = await asyncio.wait_for(blocked, timeout=10)
                assert result.outcome is Outcome.UNCHANGED
                await waiting.commit()
    finally:
        await _forget_administrators(db_engine)


async def test_the_advisory_lock_is_released_with_the_transaction(
    db_engine: AsyncEngine,
) -> None:
    email = an_email()
    try:
        await _bootstrap_committed(db_engine, email)
        async with AsyncSession(db_engine) as session:
            held = await session.execute(
                text("SELECT count(*) FROM pg_locks WHERE locktype = 'advisory'")
            )
            assert held.scalar_one() == 0
    finally:
        await _forget_administrators(db_engine)
