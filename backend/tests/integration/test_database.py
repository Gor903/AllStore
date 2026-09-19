from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings

pytestmark = pytest.mark.integration


def alembic_head() -> str:
    config = Config(str(Path(__file__).parents[2] / "alembic.ini"))
    head = ScriptDirectory.from_config(config).get_current_head()
    assert head is not None
    return head


async def test_database_is_reachable(session: AsyncSession) -> None:
    result = await session.execute(text("SELECT 1"))

    assert result.scalar_one() == 1


async def test_migrations_are_applied_up_to_head(session: AsyncSession) -> None:
    """Catches the case where a migration was added but never applied to the database."""
    version = await session.execute(text("SELECT version_num FROM alembic_version"))

    assert version.scalar_one() == alembic_head()


def test_database_url_uses_async_driver() -> None:
    assert str(get_settings().database_url).startswith("postgresql+asyncpg://")
