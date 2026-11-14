"""The background worker, and the four decisions its configuration is made of.

**JSON, never pickle.** Celery can serialise tasks with pickle, and a broker that carries
pickled objects is a broker that executes whatever is written to it. Redis here is not
exposed, but "not exposed" is a property of today's network and not of this file.

**Acknowledged late.** A task is acknowledged when it finishes rather than when it is picked
up, so a worker killed mid-letter gives the letter back to the queue instead of taking it to
the grave. The cost is a letter sent twice; the alternative is a confirmation link that never
arrives, and a person who cannot use the platform.

**One at a time.** A worker that reserved ten letters and then died would hold all ten.

**Inline with no broker.** The honest fallback: the work still happens, in the process that
asked for it, exactly as it did before the queue existed — which is also what the test suite
and a stand without Redis get.
"""

from typing import Any

import pytest

from app.worker import celery_app, enqueue, ping


def test_nothing_but_json_crosses_the_broker() -> None:
    """A broker that carries pickled objects executes whatever is written to it."""
    conf = celery_app.conf

    assert conf.task_serializer == "json"
    assert conf.accept_content == ["json"]
    assert "pickle" not in conf.accept_content


def test_a_task_is_acknowledged_when_it_is_done() -> None:
    assert celery_app.conf.task_acks_late is True


def test_a_worker_holds_one_letter_at_a_time() -> None:
    assert celery_app.conf.worker_prefetch_multiplier == 1


def test_nobody_waits_for_an_answer() -> None:
    """Storing one would be a second Redis keyspace to expire for information nobody reads."""
    assert celery_app.conf.task_ignore_result is True


def test_time_is_kept_in_one_zone() -> None:
    assert str(celery_app.conf.timezone) == "UTC"
    assert celery_app.conf.enable_utc is True


def test_the_task_modules_are_named_rather_than_discovered() -> None:
    """Autodiscovery would import them from here, and a task module imports this one for the
    app — which is a cycle."""
    assert "app.tasks.mail" in celery_app.conf.imports


def test_without_a_broker_the_work_still_happens() -> None:
    """In the process that asked for it, exactly as it did before the queue existed."""
    assert celery_app.conf.task_always_eager is True
    assert celery_app.conf.task_eager_propagates is True


def test_the_worker_can_be_asked_whether_it_is_alive() -> None:
    assert ping() == "pong"


def test_a_broker_that_is_down_does_not_undo_what_already_happened(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The caller is almost always a request that has already succeeded: the account was
    created, the password was changed, the commit happened."""

    class _Unreachable:
        name = "allstore.letter"

        def apply_async(self, **kwargs: Any) -> None:
            raise OSError("no route to broker")

    assert enqueue(_Unreachable()) is False
    assert "could not queue allstore.letter" in caplog.text


def test_and_says_so_rather_than_pretending_the_letter_is_on_its_way() -> None:
    sent: list[tuple[Any, ...]] = []

    class _Queue:
        name = "allstore.letter"

        def apply_async(self, args: tuple[Any, ...] = (), **kwargs: Any) -> None:
            sent.append(args)

    assert enqueue(_Queue(), "person@example.am") is True
    assert sent == [("person@example.am",)]
