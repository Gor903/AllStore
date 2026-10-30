"""Creates the first administrator from the environment, once.

    docker compose exec backend python -m scripts.bootstrap_admin

Reads ADMIN_EMAIL and ADMIN_PASSWORD; both must be set, and neither is ever written to the
output or the log. Safe to run on every deploy: once the platform has an administrator this
does nothing and says so.

If that administrator has lost their password — or locked themselves out — the way back in is
deliberate and local to the server:

    docker compose exec backend python -m scripts.bootstrap_admin --reset-password

which replaces the password with the current ADMIN_PASSWORD and reactivates the account. There
is no interface equivalent on purpose: it answers to whoever holds the server, not to a session.
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

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.services.admin_bootstrap import (  # noqa: E402
    BootstrapNotConfiguredError,
    bootstrap,
    write_to_a_new_administrator,
)


async def run(*, reset_password: bool) -> str:
    settings = get_settings()
    password = None if settings.admin_password is None else settings.admin_password
    engine = create_async_engine(str(settings.database_url))
    try:
        async with AsyncSession(engine) as session:
            result = await bootstrap(
                session,
                settings.admin_email,
                None if password is None else password.get_secret_value(),
                reset_password=reset_password,
            )
            await session.commit()
        write_to_a_new_administrator(settings, result)
        return result.message
    finally:
        await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--reset-password",
        action="store_true",
        help="заменить пароль существующего администратора на ADMIN_PASSWORD",
    )
    arguments = parser.parse_args()
    try:
        outcome = asyncio.run(run(reset_password=arguments.reset_password))
    except BootstrapNotConfiguredError as error:
        # the project forbids print; a script that reports to a person still has to talk
        sys.stderr.write(f"{error}\n")
        raise SystemExit(2) from error
    sys.stdout.write(f"{outcome}\n")
