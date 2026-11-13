"""The two shapes of allowance, and why they are two.

`SlidingWindow` refuses, and is keyed on where a request came from. `GraduatedDelay` slows
down, and is keyed on which account is being guessed at — a refusal keyed on somebody's email
would be a way to lock that person out using nothing but their address.
"""

import asyncio

from redis.exceptions import ConnectionError as RedisConnectionError

from app.core.rate_limit import (
    Decision,
    DelayWithALocalFallback,
    GraduatedDelay,
    SlidingWindow,
    WithALocalFallback,
)


async def test_the_allowance_is_spent_and_then_refused() -> None:
    window = SlidingWindow(limit=3, window_seconds=60.0)

    assert [(await window.check("a")).allowed for _ in range(4)] == [True, True, True, False]


async def test_keys_do_not_share_an_allowance() -> None:
    """Otherwise one noisy address would spend everybody else's attempts."""
    window = SlidingWindow(limit=1, window_seconds=60.0)

    assert (await window.check("a")).allowed is True
    assert (await window.check("b")).allowed is True
    assert (await window.check("a")).allowed is False


async def test_a_refusal_says_when_to_come_back() -> None:
    """A `Retry-After` of zero reads as an invitation rather than a limit."""
    window = SlidingWindow(limit=1, window_seconds=60.0)
    await window.check("a")

    refused = await window.check("a")

    assert refused.allowed is False
    assert 1 <= refused.retry_after_seconds <= 60


async def test_an_allowance_comes_back_once_the_window_passes() -> None:
    window = SlidingWindow(limit=1, window_seconds=0.01)
    await window.check("a")

    # the window is a fifth of the wait, so this is time passing rather than a race
    await asyncio.sleep(0.05)

    assert (await window.check("a")).allowed is True


async def test_idle_keys_are_forgotten() -> None:
    """A stream of distinct addresses must grow the table for one window, not for the life
    of the process."""
    window = SlidingWindow(limit=5, window_seconds=0.01)
    for index in range(50):
        await window.check(f"address-{index}")

    await asyncio.sleep(0.05)
    await window.check("somebody-else")

    assert len(window._hits) == 1


async def test_the_first_attempts_cost_nothing() -> None:
    """Mistyping your own password twice is the ordinary case, not an attack."""
    delay = GraduatedDelay(free_attempts=3, window_seconds=60.0, step_seconds=0.5, cap_seconds=8.0)

    assert [await delay.delay_for("a") for _ in range(3)] == [0.0, 0.0, 0.0]


async def test_the_wait_doubles_and_then_stops_growing() -> None:
    delay = GraduatedDelay(free_attempts=1, window_seconds=60.0, step_seconds=1.0, cap_seconds=4.0)
    await delay.delay_for("a")

    assert [await delay.delay_for("a") for _ in range(5)] == [1.0, 2.0, 4.0, 4.0, 4.0]


async def test_proving_the_account_is_yours_clears_what_came_before() -> None:
    """The owner who finally remembers their password should not keep paying for the guesses
    somebody else made at their address."""
    delay = GraduatedDelay(free_attempts=1, window_seconds=60.0, step_seconds=1.0, cap_seconds=8.0)
    for _ in range(4):
        await delay.delay_for("a")

    await delay.forget("a")

    assert await delay.delay_for("a") == 0.0


async def test_one_account_being_guessed_at_does_not_slow_another() -> None:
    delay = GraduatedDelay(free_attempts=1, window_seconds=60.0, step_seconds=1.0, cap_seconds=8.0)
    for _ in range(4):
        await delay.delay_for("a")

    assert await delay.delay_for("b") == 0.0


class Unreachable:
    """A shared tally with nothing behind it: Redis is down, or the network is."""

    async def check(self, key: str) -> Decision:
        raise RedisConnectionError("no route to redis")

    async def delay_for(self, key: str) -> float:
        raise RedisConnectionError("no route to redis")

    async def forget(self, key: str) -> None:
        raise RedisConnectionError("no route to redis")


async def test_redis_going_away_does_not_take_the_limiter_with_it() -> None:
    """The limiter exists to keep the platform usable under pressure. Without the fallback an
    unreachable tally came out of the dependency as a connection error, and every route behind
    a limit answered 500 — the defence became the outage."""
    limiter = WithALocalFallback(Unreachable(), SlidingWindow(limit=2, window_seconds=60.0))

    assert (await limiter.check("somebody")).allowed
    assert (await limiter.check("somebody")).allowed
    # still a tally, merely not a shared one — which is what this platform had before Redis
    assert not (await limiter.check("somebody")).allowed


async def test_the_delay_keeps_counting_in_process_too() -> None:
    delay = DelayWithALocalFallback(
        Unreachable(),
        GraduatedDelay(free_attempts=1, window_seconds=60.0, step_seconds=0.5, cap_seconds=8.0),
    )

    assert await delay.delay_for("somebody") == 0
    assert await delay.delay_for("somebody") > 0


async def test_proving_the_account_is_yours_clears_the_local_count_as_well() -> None:
    """`forget` runs on a successful sign-in. The half that cannot be reached must not stop
    the half that can from letting the owner back in at full speed."""
    delay = DelayWithALocalFallback(
        Unreachable(),
        GraduatedDelay(free_attempts=1, window_seconds=60.0, step_seconds=0.5, cap_seconds=8.0),
    )
    await delay.delay_for("somebody")
    await delay.delay_for("somebody")

    await delay.forget("somebody")

    assert await delay.delay_for("somebody") == 0
