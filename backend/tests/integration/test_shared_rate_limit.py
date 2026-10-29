"""The tally that belongs to the platform rather than to one worker.

Skipped when `REDIS_URL` says nothing, because there is then nothing to talk to. CI runs a
Redis for exactly this file — a shared limiter that nobody tests is a limiter nobody knows
the shape of, and the shape is the point: an in-process tally quietly doubles the allowance
the moment a second worker appears.
"""

import asyncio
import os
import uuid
from collections.abc import AsyncIterator

import pytest
from redis.asyncio import Redis

from app.core.rate_limit import SharedDelay, SharedWindow

pytestmark = pytest.mark.integration

REDIS_URL = os.environ.get("REDIS_URL", "")


@pytest.fixture
async def redis() -> AsyncIterator[Redis]:
    if not REDIS_URL:
        pytest.skip("REDIS_URL is unset, so there is no shared tally to test")
    client: Redis = Redis.from_url(REDIS_URL, decode_responses=True)
    try:
        yield client
    finally:
        await client.aclose()


def _name() -> str:
    """A fresh namespace per test: the keys outlive a test by design, and two runs of the
    suite must not meet each other's attempts."""
    return f"test-{uuid.uuid4().hex}"


async def test_the_allowance_is_spent_and_then_refused(redis: Redis) -> None:
    window = SharedWindow(redis, _name(), limit=3, window_seconds=60.0)

    answers = [(await window.check("a")).allowed for _ in range(4)]

    assert answers == [True, True, True, False]


async def test_keys_do_not_share_an_allowance(redis: Redis) -> None:
    window = SharedWindow(redis, _name(), limit=1, window_seconds=60.0)

    assert (await window.check("a")).allowed is True
    assert (await window.check("b")).allowed is True
    assert (await window.check("a")).allowed is False


async def test_two_workers_share_one_tally(redis: Redis) -> None:
    """The whole reason this exists. Two limiters, one name, one allowance between them."""
    name = _name()
    one = SharedWindow(redis, name, limit=2, window_seconds=60.0)
    another = SharedWindow(redis, name, limit=2, window_seconds=60.0)

    assert (await one.check("a")).allowed is True
    assert (await another.check("a")).allowed is True
    assert (await one.check("a")).allowed is False


async def test_a_refused_attempt_does_not_extend_the_window(redis: Redis) -> None:
    """Matching the in-process shape: hammering must not keep the door shut forever, or a
    persistent mistake would outlast the window that was supposed to forgive it."""
    window = SharedWindow(redis, _name(), limit=1, window_seconds=1.0)
    await window.check("a")
    for _ in range(5):
        await window.check("a")

    await asyncio.sleep(1.2)

    assert (await window.check("a")).allowed is True


async def test_a_refusal_says_when_to_come_back(redis: Redis) -> None:
    window = SharedWindow(redis, _name(), limit=1, window_seconds=60.0)
    await window.check("a")

    refused = await window.check("a")

    assert refused.allowed is False
    assert 1 <= refused.retry_after_seconds <= 60


async def test_a_simultaneous_rush_still_lets_through_only_the_allowance(
    redis: Redis,
) -> None:
    """The race the Lua script exists to lose: read the count and act on it in one step, so
    two callers cannot both find room that only one of them has."""
    window = SharedWindow(redis, _name(), limit=5, window_seconds=60.0)

    answers = await asyncio.gather(*(window.check("a") for _ in range(20)))

    assert sum(1 for answer in answers if answer.allowed) == 5


async def test_the_first_attempts_cost_nothing(redis: Redis) -> None:
    delay = SharedDelay(
        redis, _name(), free_attempts=3, window_seconds=60.0, step_seconds=0.5, cap_seconds=8.0
    )

    assert [await delay.delay_for("a") for _ in range(3)] == [0.0, 0.0, 0.0]


async def test_the_wait_doubles_and_then_stops_growing(redis: Redis) -> None:
    delay = SharedDelay(
        redis, _name(), free_attempts=1, window_seconds=60.0, step_seconds=1.0, cap_seconds=4.0
    )
    await delay.delay_for("a")

    assert [await delay.delay_for("a") for _ in range(5)] == [1.0, 2.0, 4.0, 4.0, 4.0]


async def test_proving_the_account_is_yours_clears_what_came_before(redis: Redis) -> None:
    delay = SharedDelay(
        redis, _name(), free_attempts=1, window_seconds=60.0, step_seconds=1.0, cap_seconds=8.0
    )
    for _ in range(4):
        await delay.delay_for("a")

    await delay.forget("a")

    assert await delay.delay_for("a") == 0.0


async def test_the_keys_let_go_of_themselves(redis: Redis) -> None:
    """Nothing sweeps this table, so every key has to carry its own end."""
    name = _name()
    window = SharedWindow(redis, name, limit=5, window_seconds=30.0)

    await window.check("a")

    assert 0 < await redis.ttl(f"rl:{name}:a") <= 31
