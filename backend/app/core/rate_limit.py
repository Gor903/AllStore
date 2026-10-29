"""Allowances for the few routes that must not be hammered.

Two shapes, because two different things are being defended.

`SlidingWindow` refuses. It is keyed on where a request came from, and the worst a refusal
can do to somebody is make them wait — they can mistype their own password from another
address, or in a minute.

`GraduatedDelay` slows down instead, and exists because the other shape cannot be keyed on an
email address. A refusal keyed on somebody's address is a way to lock that person out using
nothing but their address: burn the allowance and the owner is shut out of their own account.
A delay costs the sender their time and leaves the owner a door that still opens.

Each has two implementations behind one protocol. In process, the tally belongs to one worker
and dies with it — honest for a single-worker deployment and wrong the moment a second one
appears, because the allowance silently doubles. On Redis it is one tally for the whole
platform. Which one runs is a matter of whether `REDIS_URL` is set, and nothing else in the
application knows the difference.

The answers are `async` for the sake of the second implementation. The first does no waiting
at all and could have stayed synchronous — at the cost of two protocols, two sets of
dependencies and a choice that leaked into every caller.
"""

import math
import time
from collections import deque
from contextlib import suppress
from dataclasses import dataclass
from typing import Protocol

from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class Decision:
    allowed: bool
    # what to put in `Retry-After`: whole seconds, and never zero when refusing, because a
    # header telling somebody to retry immediately is an invitation rather than a limit
    retry_after_seconds: int


ALLOWED = Decision(allowed=True, retry_after_seconds=0)


class Allowance(Protocol):
    """What a limiter has to answer, whoever is keeping the tally."""

    async def check(self, key: str) -> Decision: ...


class Delay(Protocol):
    """How long this key should be made to wait before it is served."""

    async def delay_for(self, key: str) -> float: ...

    async def forget(self, key: str) -> None: ...


class SlidingWindow:
    """One worker's own tally. See the module docstring for what that is and is not worth."""

    def __init__(self, limit: int, window_seconds: float) -> None:
        self._limit = limit
        self._window = window_seconds
        self._hits: dict[str, deque[float]] = {}

    async def check(self, key: str) -> Decision:
        """Records an attempt and says whether it was within the allowance."""
        now = time.monotonic()
        self._forget_stale(now)
        hits = self._hits.setdefault(key, deque())
        while hits and hits[0] <= now - self._window:
            hits.popleft()
        if len(hits) >= self._limit:
            # the allowance comes back when the oldest attempt leaves the window
            waiting = self._window - (now - hits[0])
            return Decision(allowed=False, retry_after_seconds=max(1, math.ceil(waiting)))
        hits.append(now)
        return ALLOWED

    def _forget_stale(self, now: float) -> None:
        """Keys nobody has used for a whole window are dropped, so a stream of distinct
        addresses grows the table for one window rather than for the life of the process."""
        stale = [
            key for key, hits in self._hits.items() if not hits or hits[-1] <= now - self._window
        ]
        for key in stale:
            del self._hits[key]


class GraduatedDelay:
    """How long this key should be made to wait before it is served.

    The first few attempts are free: somebody mistyping their own password twice is the
    ordinary case, and punishing it would be felt by almost nobody except the people it is
    not aimed at. After that the wait doubles each time, up to a cap — long enough that
    guessing in bulk stops being worth anybody's afternoon, short enough that the owner who
    finally remembers their password still gets in.
    """

    def __init__(
        self, free_attempts: int, window_seconds: float, step_seconds: float, cap_seconds: float
    ) -> None:
        self._free = free_attempts
        self._window = window_seconds
        self._step = step_seconds
        self._cap = cap_seconds
        self._hits: dict[str, deque[float]] = {}

    async def delay_for(self, key: str) -> float:
        now = time.monotonic()
        self._forget_stale(now)
        hits = self._hits.setdefault(key, deque())
        while hits and hits[0] <= now - self._window:
            hits.popleft()
        hits.append(now)
        return _wait_for(len(hits), self._free, self._step, self._cap)

    async def forget(self, key: str) -> None:
        """Called when the attempt turned out to be the owner's: the account they just proved
        they own should not keep paying for the guesses that came before them."""
        self._hits.pop(key, None)

    def _forget_stale(self, now: float) -> None:
        stale = [
            key for key, hits in self._hits.items() if not hits or hits[-1] <= now - self._window
        ]
        for key in stale:
            del self._hits[key]


def _wait_for(attempts: int, free: int, step: float, cap: float) -> float:
    over = attempts - free
    if over <= 0:
        return 0.0
    return min(cap, step * float(2 ** (over - 1)))


# Trim what has fallen out of the window, count what is left, and record this attempt —
# but only if there is room, which is the one thing a pipeline cannot express. Two workers
# reading the same count and both deciding they are under the limit is exactly the race this
# exists to lose. A limit below zero means "always record": the delay shape has no ceiling.
_RECORD = """
local key = KEYS[1]
local now, window = tonumber(ARGV[1]), tonumber(ARGV[2])
local limit, member = tonumber(ARGV[3]), ARGV[4]
redis.call('ZREMRANGEBYSCORE', key, 0, now - window)
local count = redis.call('ZCARD', key)
local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
local oldest_age = '0'
if oldest[2] then oldest_age = tostring(now - tonumber(oldest[2])) end
if limit >= 0 and count >= limit then
  return {count, oldest_age, 0}
end
redis.call('ZADD', key, now, member)
redis.call('EXPIRE', key, math.ceil(window) + 1)
return {count + 1, oldest_age, 1}
"""


class _Counted:
    """The shared half of both shapes: how many times this key has been seen lately.

    A sorted set of timestamps rather than a counter, because a counter is a fixed window and
    a fixed window lets twice the allowance through at the seam between two of them.

    The key expires on its own. Nothing sweeps this table, and nothing should have to.
    """

    def __init__(self, redis: Redis, name: str, window_seconds: float) -> None:
        self._redis = redis
        self._name = name
        self._window = window_seconds
        self._record = redis.register_script(_RECORD)

    async def record(self, key: str, limit: int) -> tuple[int, float, bool]:
        """How many attempts are in the window, the age of the oldest, and whether this one
        was recorded at all.

        The last has to be said out loud: on a refusal the count is the one from before the
        attempt, so a refused caller and the last admitted one report the same number.
        """
        now = time.time()
        result = await self._record(
            keys=[f"rl:{self._name}:{key}"],
            args=[now, self._window, limit, f"{now}:{time.monotonic_ns()}"],
        )
        count, oldest_age, recorded = result
        return int(count), float(oldest_age), bool(int(recorded))

    async def drop(self, key: str) -> None:
        await self._redis.delete(f"rl:{self._name}:{key}")


class SharedWindow:
    """`SlidingWindow` with the tally where every worker can see it."""

    def __init__(self, redis: Redis, name: str, limit: int, window_seconds: float) -> None:
        self._counted = _Counted(redis, name, window_seconds)
        self._limit = limit
        self._window = window_seconds

    async def check(self, key: str) -> Decision:
        _, oldest_age, recorded = await self._counted.record(key, self._limit)
        if recorded:
            return ALLOWED
        # the allowance comes back when the oldest attempt leaves the window
        return Decision(
            allowed=False, retry_after_seconds=max(1, math.ceil(self._window - oldest_age))
        )


class SharedDelay:
    """`GraduatedDelay` with the tally where every worker can see it."""

    def __init__(
        self,
        redis: Redis,
        name: str,
        free_attempts: int,
        window_seconds: float,
        step_seconds: float,
        cap_seconds: float,
    ) -> None:
        self._counted = _Counted(redis, name, window_seconds)
        self._free = free_attempts
        self._step = step_seconds
        self._cap = cap_seconds

    async def delay_for(self, key: str) -> float:
        # no ceiling: this shape slows down rather than refusing, so every attempt counts
        count, _, _ = await self._counted.record(key, -1)
        return _wait_for(count, self._free, self._step, self._cap)

    async def forget(self, key: str) -> None:
        await self._counted.drop(key)


class WithALocalFallback:
    """A shared allowance with a per-worker one standing behind it.

    Redis going away must not take the site with it. Before this, an unreachable tally came
    out of the dependency as a connection error and every route carrying a limit answered 500
    — which is to say the rate limiter, whose job is to keep the platform available under
    pressure, became the thing that made it unavailable.

    Falling back to the in-process tally rather than to nothing: an allowance that is merely
    per-worker is what this platform had before Redis existed and is far better than none,
    because "none" means an outage of the cache is also an open door. The fallback keeps its
    own counts, so it starts from zero — on purpose. Inheriting a number it cannot see would
    be inventing one.
    """

    def __init__(self, shared: Allowance, local: Allowance) -> None:
        self._shared = shared
        self._local = local

    async def check(self, key: str) -> Decision:
        try:
            return await self._shared.check(key)
        except RedisError:
            logger.warning("the shared rate-limit tally is unreachable; counting in process")
            return await self._local.check(key)


class DelayWithALocalFallback:
    """The same arrangement for the shape that slows down instead of refusing."""

    def __init__(self, shared: Delay, local: Delay) -> None:
        self._shared = shared
        self._local = local

    async def delay_for(self, key: str) -> float:
        try:
            return await self._shared.delay_for(key)
        except RedisError:
            logger.warning("the shared rate-limit tally is unreachable; counting in process")
            return await self._local.delay_for(key)

    async def forget(self, key: str) -> None:
        with suppress(RedisError):
            await self._shared.forget(key)
        # Always, and not only on failure: an attempt may have been counted locally while
        # Redis was away, and the person has just proved the account is theirs.
        await self._local.forget(key)
