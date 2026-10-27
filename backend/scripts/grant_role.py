"""Gives an account a role nobody can register into, and creates it if it is not there.

    docker compose exec backend python -m scripts.grant_role moderator@example.com secret moderator

Break-glass, not the normal path. A moderator is appointed by an administrator through a
personal invitation (`/admin/moderators`); this exists for the cases where there is no
administrator to do it yet, and for the end-to-end suite, which needs a moderator before it
has a browser. Re-running is safe: an existing account keeps its password and only changes role.

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


async def grant(email: str, password: str, role: UserRole) -> str:
    engine = create_async_engine(str(get_settings().database_url))
    try:
        async with AsyncSession(engine) as session:
            found = await session.execute(select(User).where(User.email == email))
            user = found.scalar_one_or_none()
            if user is None:
                session.add(User(email=email, password_hash=hash_password(password), role=role))
                what = "создан"
            elif user.role is role:
                return f"{email}: уже {role.value}, ничего не менялось"
            else:
                was = user.role.value
                user.role = role
                what = f"был {was}"
            await session.commit()
            return f"{email}: {role.value} ({what})"
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
    arguments = parser.parse_args()
    outcome = asyncio.run(grant(arguments.email, arguments.password, UserRole(arguments.role)))
    # the project forbids print; a script that reports to a person still has to talk
    sys.stdout.write(f"{outcome}\n")
