"""Allowances for the few routes that must not be hammered.

In process and in memory, which is an honest description of the reach: with several workers
each keeps its own tally, and a restart forgets everything. The deployment runs one worker,
so today that tally is the whole application — but the day a second one appears the allowance
doubles silently, which is why `Allowance` is a protocol and not just this class. A shared
tally arrives with the store the build plan already reserves for the background queue.

Two shapes, because two different things are being defended.

`SlidingWindow` refuses. It is keyed on where a request came from, and the worst a refusal
can do to somebody is make them wait — they can mistype their own password from another
address, or in a minute.

`GraduatedDelay` slows down instead, and exists because the other shape cannot be keyed on an
email address. A refusal keyed on somebody's address is a way to lock that person out using
nothing but their address: burn the allowance and the owner is shut out of their own account.
A delay costs the sender their time and leaves the owner a door that still opens.
"""

import math
import time
from collections import deque
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class Decision:
    allowed: bool
    # what to put in `Retry-After`: whole seconds, and never zero when refusing, because a
    # header telling somebody to retry immediately is an invitation rather than a limit
    retry_after_seconds: int


ALLOWED = Decision(allowed=True, retry_after_seconds=0)


class Allowance(Protocol):
    """What a limiter has to answer. The shared implementation will answer the same thing."""

    def check(self, key: str) -> Decision: ...


class SlidingWindow:
    def __init__(self, limit: int, window_seconds: float) -> None:
        self._limit = limit
        self._window = window_seconds
        self._hits: dict[str, deque[float]] = {}

    def check(self, key: str) -> Decision:
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

    def delay_for(self, key: str) -> float:
        now = time.monotonic()
        self._forget_stale(now)
        hits = self._hits.setdefault(key, deque())
        while hits and hits[0] <= now - self._window:
            hits.popleft()
        hits.append(now)
        over = len(hits) - self._free
        if over <= 0:
            return 0.0
        return min(self._cap, self._step * float(2 ** (over - 1)))

    def forget(self, key: str) -> None:
        """Called when the attempt turned out to be the owner's: the account they just proved
        they own should not keep paying for the guesses that came before them."""
        self._hits.pop(key, None)

    def _forget_stale(self, now: float) -> None:
        stale = [
            key for key, hits in self._hits.items() if not hits or hits[-1] <= now - self._window
        ]
        for key in stale:
            del self._hits[key]
