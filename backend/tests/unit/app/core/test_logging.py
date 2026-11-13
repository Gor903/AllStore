"""How the platform is set up to talk, and why each line appears exactly once.

Logging is global state, so these tests put it back the way they found it. A test that leaves
the root logger at DEBUG does not fail — it makes the next test print a thousand lines of
SQLAlchemy, and whoever runs the suite blames their own change.
"""

import logging
from collections.abc import Iterator

import pytest

from app.core.logging import configure_logging, get_logger

MANAGED = ("uvicorn", "uvicorn.access")


@pytest.fixture(autouse=True)
def _restore_logging() -> Iterator[None]:
    """Snapshot and put back: the logging configuration is global for the whole process."""
    root = logging.getLogger()
    before = (root.level, list(root.handlers))
    managed = {name: logging.getLogger(name) for name in MANAGED}
    managed_before = {
        name: (logger.level, list(logger.handlers), logger.propagate)
        for name, logger in managed.items()
    }

    yield

    root.setLevel(before[0])
    root.handlers = before[1]
    for name, (level, handlers, propagate) in managed_before.items():
        logger = managed[name]
        logger.setLevel(level)
        logger.handlers = handlers
        logger.propagate = propagate


@pytest.mark.parametrize(("asked", "expected"), [("debug", 10), ("INFO", 20), ("warning", 30)])
def test_the_level_is_read_however_it_was_written(asked: str, expected: int) -> None:
    """It comes from `LOG_LEVEL` in the environment, and a person writes that."""
    configure_logging(asked)

    assert logging.getLogger().level == expected


def test_everything_goes_to_the_console() -> None:
    """One handler, on purpose: the platform runs in containers, and a file inside one is a
    log nobody reads — the collector reads the stream (see infra/observability)."""
    configure_logging("info")

    handlers = logging.getLogger().handlers
    assert len(handlers) == 1
    assert isinstance(handlers[0], logging.StreamHandler)


def test_a_line_carries_when_how_loud_and_from_where() -> None:
    """Without the name, a warning from the rate limiter and one from the mailer are the same
    line to whoever is reading at three in the morning."""
    configure_logging("info")
    formatter = logging.getLogger().handlers[0].formatter
    assert formatter is not None

    record = logging.LogRecord(
        "app.core.mail", logging.WARNING, __file__, 1, "письмо не ушло", None, None
    )

    rendered = formatter.format(record)

    assert "WARNING" in rendered
    assert "app.core.mail" in rendered
    assert "письмо не ушло" in rendered


@pytest.mark.parametrize("name", MANAGED)
def test_the_server_s_own_lines_are_not_printed_twice(name: str) -> None:
    """uvicorn configures itself and would hand its records to the root logger as well, so
    every request line would appear once from uvicorn and once from here."""
    configure_logging("info")

    assert logging.getLogger(name).propagate is False
    assert logging.getLogger(name).handlers


def test_a_library_that_set_itself_up_before_us_keeps_working() -> None:
    """`disable_existing_loggers: False`. With the default, any logger created at import time
    — which is most of them — would be silenced by this call, and the platform would start up
    into silence."""
    early = get_logger("some.library.configured.early")

    configure_logging("info")

    assert early.disabled is False


def test_a_module_asks_for_a_logger_by_its_own_name() -> None:
    assert get_logger("app.core.mail").name == "app.core.mail"
    assert get_logger(__name__) is logging.getLogger(__name__)
