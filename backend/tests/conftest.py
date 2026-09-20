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
}
for key, value in _DEFAULTS.items():
    os.environ.setdefault(key, value)


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
