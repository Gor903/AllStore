import pytest
from sqlalchemy import text

from app.core.config import get_settings
from app.db.session import dispose_engine, get_sessionmaker

pytestmark = pytest.mark.integration


async def test_database_is_reachable() -> None:
    async with get_sessionmaker()() as session:
        result = await session.execute(text("SELECT 1"))

        assert result.scalar_one() == 1

    await dispose_engine()


async def test_migrations_were_applied() -> None:
    """alembic upgrade head must have run against this database before the suite."""
    async with get_sessionmaker()() as session:
        version = await session.execute(text("SELECT version_num FROM alembic_version"))

        assert version.scalar_one() == "0001"

    await dispose_engine()


def test_database_url_uses_async_driver() -> None:
    assert str(get_settings().database_url).startswith("postgresql+asyncpg://")
