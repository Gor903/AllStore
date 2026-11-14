"""One engine and one sessionmaker per process, made on first use.

A connection pool per request would be a pool of pools: every request paying for a handshake
and the database holding a connection for each of them. Making it lazily rather than at import
keeps a module that merely imports this one from opening a socket — which is what lets the
test suite, Alembic and the worker import the application without a database behind them.

`pool_pre_ping` is the one setting here that answers a real event: a connection that the
database closed while nobody was looking comes back as an error on the next query, and the
visitor sees a five hundred for a query that was perfectly good.
"""

from typing import Any

import pytest
from sqlalchemy.pool import QueuePool

from app.core.config import Settings, get_settings
from app.db import session as db


def _settings(**overrides: Any) -> Settings:
    return get_settings().model_copy(update=overrides)


@pytest.fixture(autouse=True)
def _forget_the_engine() -> Any:
    """This module is process-wide state; a test that made an engine puts it back."""
    db._engine = None
    db._sessionmaker = None
    yield
    db._engine = None
    db._sessionmaker = None


def test_the_engine_is_made_once_and_shared() -> None:
    assert db.get_engine(_settings()) is db.get_engine()


def test_the_sessionmaker_is_too() -> None:
    assert db.get_sessionmaker() is db.get_sessionmaker()


def test_the_engine_is_configured_from_the_settings() -> None:
    engine = db.get_engine(_settings(db_pool_size=7))
    pool = engine.pool
    assert isinstance(pool, QueuePool)

    assert pool.size() == 7


def test_a_connection_is_checked_before_it_is_handed_out() -> None:
    """A connection the database closed while nobody was looking comes back as an error on
    the next query — and the visitor sees a five hundred for a query that was fine."""
    pool = db.get_engine(_settings()).pool
    assert isinstance(pool, QueuePool)

    assert pool._pre_ping is True


def test_nothing_is_opened_until_somebody_asks() -> None:
    """Which is what lets Alembic, the worker and the test suite import the application
    without a database behind them."""
    assert db._engine is None


async def test_disposing_lets_the_next_caller_start_again() -> None:
    first = db.get_engine(_settings())

    await db.dispose_engine()

    assert db._engine is None
    assert db.get_engine(_settings()) is not first


async def test_disposing_twice_is_not_an_error() -> None:
    """Shutdown runs it, and a shutdown that ran after a failed start-up would otherwise be
    a second failure on top of the first."""
    await db.dispose_engine()
    await db.dispose_engine()


def test_an_object_is_still_readable_after_the_commit_that_saved_it() -> None:
    """`expire_on_commit=False`. With the default, every attribute read after a commit is a
    fresh query — and in async that is a query nobody awaited, which raises instead."""
    assert db.get_sessionmaker().kw["expire_on_commit"] is False
