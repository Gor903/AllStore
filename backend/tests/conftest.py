import os
from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient

# Defaults let the suite run without a shell setup; CI and compose override them via env.
_DEFAULTS = {
    "APP_ENV": "local",
    "SECRET_KEY": "test-secret-not-for-real-use",
    "DATABASE_URL": "postgresql+asyncpg://allstore:allstore@localhost:5433/allstore",
    "S3_ENDPOINT_URL": "http://localhost:9000",
    "S3_ACCESS_KEY": "minioadmin",
    "S3_SECRET_KEY": "minioadmin",
    "S3_BUCKET": "allstore-dev",
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
