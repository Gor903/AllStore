from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import Settings

_sessions: async_sessionmaker[AsyncSession] | None = None
_engine: AsyncEngine | None = None


def configure(settings: Settings) -> None:
    global _engine, _sessions
    _engine = create_async_engine(str(settings.database_url), echo=settings.db_echo)
    _sessions = async_sessionmaker(_engine, expire_on_commit=False)


async def dispose() -> None:
    global _engine, _sessions
    if _engine is not None:
        await _engine.dispose()
    _engine, _sessions = None, None


def session_factory() -> async_sessionmaker[AsyncSession]:
    if _sessions is None:
        raise RuntimeError("База не настроена: configure() не вызван")
    return _sessions


async def get_session() -> AsyncIterator[AsyncSession]:
    async with session_factory()() as session:
        yield session
