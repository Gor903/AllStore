import os
from collections.abc import AsyncIterator, Iterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

# Defaults let the suite run without a shell setup; CI and compose override them via env.
_DEFAULTS = {
    "APP_ENV": "local",
    "SECRET_KEY": "test-secret-not-for-real-use-32-chars-min",
    "DATABASE_URL": "postgresql+asyncpg://allstore:allstore@localhost:5433/allstore",
    "S3_ENDPOINT_URL": "http://localhost:9000",
    "S3_ACCESS_KEY": "minioadmin",
    "S3_SECRET_KEY": "minioadmin",
    "S3_BUCKET": "allstore-dev",
    # production argon2 parameters spend 19 MiB per hash — that costs minutes across a suite
    "ARGON2_MEMORY_COST": "64",
    "ARGON2_TIME_COST": "1",
    # the suite talks to nobody: an outage elsewhere must not turn into a red build here
    "BREACHED_PASSWORD_URL": "",
}
for key, value in _DEFAULTS.items():
    os.environ.setdefault(key, value)

# Background work happens inline here, whatever the environment says.
#
# Not left to the fallback in app/worker.py, which turns eager mode on only when no broker is
# configured: CI sets REDIS_URL for the rate-limiter tests, and without this line the suite
# would quietly start putting letters on a real queue that nothing reads — green either way,
# and testing nothing. A test that wants to know whether something was queued says so.
from app.worker import celery_app  # noqa: E402 — the settings above have to be in place first

celery_app.conf.task_always_eager = True
celery_app.conf.task_eager_propagates = True


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    """ASGI client without lifespan — unit tests must not depend on Postgres or S3."""
    from app.main import create_app

    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as async_client:
        yield async_client


@pytest.fixture
async def api_client(session: "AsyncSession") -> AsyncIterator[AsyncClient]:
    """Client whose requests run inside the test transaction, so endpoints leave no rows behind."""
    from app.db.session import get_session
    from app.main import create_app

    app = create_app()

    async def _use_test_session() -> AsyncSession:
        return session

    app.dependency_overrides[get_session] = _use_test_session
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as async_client:
        yield async_client


@pytest.fixture
async def committing_api_client(db_engine: "AsyncEngine") -> AsyncIterator[AsyncClient]:
    """Client whose requests commit for real, and whose session is torn down for real.

    `api_client` hands the endpoint a session **object**, so the dependency never closes and
    the outer transaction swallows every commit. That is right for most tests and wrong for
    one question: whether a write survives the request it was made in. A handler that writes
    and then raises looks identical either way under `api_client` — the rollback that discards
    the write is precisely what the shared session cannot perform.

    Here the dependency stays a generator, so FastAPI throws the exception into it exactly as
    it does in production, and the session closes with the transaction it was given. Nothing
    rolls the test back afterwards, hence the truncate.
    """
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from app.db.session import get_session
    from app.main import create_app

    app = create_app()
    sessionmaker = async_sessionmaker(db_engine, expire_on_commit=False)

    async def _real_lifecycle() -> AsyncIterator[AsyncSession]:
        async with sessionmaker() as db_session:
            yield db_session

    app.dependency_overrides[get_session] = _real_lifecycle
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as async_client:
            yield async_client
    finally:
        await _empty_every_table(db_engine)


@pytest.fixture
async def fresh_session(db_engine: "AsyncEngine") -> AsyncIterator[AsyncSession]:
    """A session that has seen nothing of the request — what the next caller would see.

    Reading through the session an endpoint used would answer "was it written?" with what is
    merely pending in that transaction. This one asks the database.
    """
    async with AsyncSession(db_engine, expire_on_commit=False) as db_session:
        yield db_session


# Rows that a migration put there, not a test. `categories` is the starting catalogue from
# migration 0004, and half the suite reads it through `seeded_category`; emptying it leaves a
# database that no migration will fill again, because the migration has already run. The other
# two migrations that insert (0016, 0021) backfill from existing rows and seed nothing.
SEEDED_BY_MIGRATION = frozenset({"categories"})


async def _empty_every_table(engine: "AsyncEngine") -> None:
    """Removes what the test wrote and nothing else.

    `alembic_version` is outside the metadata and so is left alone by construction: the schema
    outlives the rows.
    """
    from sqlalchemy import text

    from app.db.base import Base

    names = ", ".join(
        f'"{table.name}"'
        for table in Base.metadata.sorted_tables
        if table.name not in SEEDED_BY_MIGRATION
    )
    async with engine.begin() as connection:
        await connection.execute(text(f"TRUNCATE {names} RESTART IDENTITY CASCADE"))


@pytest.fixture
def object_storage() -> Iterator[None]:
    """A bucket backed by moto, so the real boto3 path runs without infrastructure.

    moto hooks botocore by endpoint, so the bucket is addressed as AWS here instead of as
    the MinIO of the dev stack. Everything above that line — the client, the upload, the
    key, the deletion — is the code that runs in production.
    """
    from moto import mock_aws

    from app.core.config import get_settings

    previous = os.environ.get("S3_ENDPOINT_URL")
    os.environ["S3_ENDPOINT_URL"] = "https://s3.us-east-1.amazonaws.com"
    get_settings.cache_clear()
    try:
        with mock_aws():
            from app.core.storage import build_s3_client

            build_s3_client(get_settings()).create_bucket(Bucket=get_settings().s3_bucket)
            yield
    finally:
        if previous is None:
            del os.environ["S3_ENDPOINT_URL"]
        else:
            os.environ["S3_ENDPOINT_URL"] = previous
        get_settings.cache_clear()


@pytest.fixture
async def db_engine() -> AsyncIterator[AsyncEngine]:
    """One engine per test: each test runs its own event loop, so a pool cannot be shared."""
    from app.core.config import get_settings

    engine = create_async_engine(str(get_settings().database_url), poolclass=NullPool)
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest.fixture
async def session(db_engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    """The test runs inside an outer transaction that is rolled back, leaving the database clean."""
    async with db_engine.connect() as connection:
        transaction = await connection.begin()
        db_session = AsyncSession(
            bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint"
        )
        try:
            yield db_session
        finally:
            await db_session.close()
            await transaction.rollback()
