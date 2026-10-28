"""Gives an account a role nobody can register into, and creates it if it is not there.

    docker compose exec backend python -m scripts.grant_role moderator@example.com secret moderator

Break-glass, not the normal path. A moderator is appointed by an administrator through a
personal invitation (`/admin/moderators`); this exists for the cases where there is no
administrator to do it yet, and for the end-to-end suite, which needs a moderator before it
has a browser. Re-running is safe: an existing account keeps its password and only changes role.

A password given on a command line is known to whoever typed it, so an account created here
has to replace it before it can do anything — the same rule as an administrator bootstrapped
from the environment. An account that already existed is not asked: its password is its own.

`--reset-password` is the way back in for a moderator who lost theirs, and it hands over a
password the same way the first run does — so it expires the same way.

The administrator role is not granted here — there is exactly one, and it comes from
`scripts.bootstrap_admin`, which is idempotent and takes a lock.
"""

import argparse
import asyncio
import os
import sys

# the defaults of the compose stack, so the script runs with no shell setup
_DEFAULTS = {
    "APP_ENV": "local",
    "SECRET_KEY": "dev-secret-change-me-not-for-production",
    "DATABASE_URL": "postgresql+asyncpg://allstore:allstore@localhost:5433/allstore",
    "S3_ENDPOINT_URL": "http://localhost:9000",
    "S3_ACCESS_KEY": "minioadmin",
    "S3_SECRET_KEY": "minioadmin",
    "S3_BUCKET": "allstore-dev",
}
for _key, _value in _DEFAULTS.items():
    os.environ.setdefault(_key, _value)

from sqlalchemy import select  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.models import User, UserRole  # noqa: E402


async def apply(
    session: AsyncSession,
    email: str,
    password: str,
    role: UserRole,
    *,
    reset_password: bool = False,
) -> str:
    """Creates the account or moves an existing one into the role. Returns what to tell the
    operator; the caller owns the session and the commit."""
    found = await session.execute(select(User).where(User.email == email))
    user = found.scalar_one_or_none()
    if user is None:
        session.add(
            User(
                email=email,
                password_hash=hash_password(password),
                role=role,
                # the password was typed on somebody else's command line, so it gets the
                # account in once and no further — same rule as an administrator bootstrapped
                # from the environment
                must_change_password=True,
            )
        )
        return f"{email}: {role.value} (создан, пароль временный)"
    if reset_password:
        user.role = role
        user.password_hash = hash_password(password)
        # handed over again, so it expires again
        user.must_change_password = True
        return f"{email}: {role.value} (пароль заменён, временный)"
    if user.role is role:
        return f"{email}: уже {role.value}, ничего не менялось"
    was = user.role.value
    user.role = role
    # not touched: this account chose its own password long before anybody granted it a role
    return f"{email}: {role.value} (был {was})"


async def grant(email: str, password: str, role: UserRole, *, reset_password: bool) -> str:
    engine = create_async_engine(str(get_settings().database_url))
    try:
        async with AsyncSession(engine) as session:
            outcome = await apply(session, email, password, role, reset_password=reset_password)
            await session.commit()
            return outcome
    finally:
        await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("email")
    parser.add_argument("password", help="используется только при создании аккаунта")
    parser.add_argument(
        "role",
        # admin is missing on purpose: the platform has one, and it is bootstrapped
        choices=[role.value for role in UserRole if role is not UserRole.ADMIN],
    )
    parser.add_argument(
        "--reset-password",
        action="store_true",
        help="заменить пароль существующего аккаунта на указанный (он станет временным)",
    )
    arguments = parser.parse_args()
    outcome = asyncio.run(
        grant(
            arguments.email,
            arguments.password,
            UserRole(arguments.role),
            reset_password=arguments.reset_password,
        )
    )
    # the project forbids print; a script that reports to a person still has to talk
    sys.stdout.write(f"{outcome}\n")
