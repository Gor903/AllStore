"""A small sliding-window limiter for the few routes that must not be hammered.

In process and in memory, which is an honest description of its reach: with several workers
the allowance is per worker, and it resets on restart. That is enough for what it guards —
the invitation form, whose token is 32 random bytes and therefore not guessable in any number
of attempts this would ever permit. The limiter is here to make a flood pointless and to keep
the password hasher from being used as a treadmill, not to be the thing standing between an
attacker and a moderator account.

A shared allowance across workers arrives with Redis, together with the background queue the
build plan already reserves it for (раздел 11, пункт 11).
"""

import time
from collections import deque


class SlidingWindow:
    def __init__(self, limit: int, window_seconds: float) -> None:
        self._limit = limit
        self._window = window_seconds
        self._hits: dict[str, deque[float]] = {}

    def allow(self, key: str) -> bool:
        """Records an attempt and says whether it is within the allowance."""
        now = time.monotonic()
        self._forget_stale(now)
        hits = self._hits.setdefault(key, deque())
        while hits and hits[0] <= now - self._window:
            hits.popleft()
        if len(hits) >= self._limit:
            return False
        hits.append(now)
        return True

    def _forget_stale(self, now: float) -> None:
        """Keys nobody has used for a whole window are dropped, so a stream of distinct
        addresses grows the table for one window rather than for the life of the process."""
        stale = [
            key for key, hits in self._hits.items() if not hits or hits[-1] <= now - self._window
        ]
        for key in stale:
            del self._hits[key]
