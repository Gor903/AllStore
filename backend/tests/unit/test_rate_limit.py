import time

from app.core.rate_limit import SlidingWindow


def test_the_allowance_is_spent_and_then_refused() -> None:
    window = SlidingWindow(limit=3, window_seconds=60)

    assert [window.allow("caller") for _ in range(4)] == [True, True, True, False]


def test_each_caller_has_their_own_allowance() -> None:
    """Keyed on the caller, not on what they sent: one key for everybody would let anyone
    lock everybody else out by filling the window themselves."""
    window = SlidingWindow(limit=1, window_seconds=60)

    assert window.allow("first") is True
    assert window.allow("second") is True
    assert window.allow("first") is False


def test_the_allowance_comes_back_once_the_window_has_passed() -> None:
    window = SlidingWindow(limit=1, window_seconds=0.05)
    assert window.allow("caller") is True

    time.sleep(0.06)

    assert window.allow("caller") is True


def test_callers_nobody_has_seen_for_a_window_are_forgotten() -> None:
    """Otherwise a stream of distinct addresses grows the table for the life of the process."""
    window = SlidingWindow(limit=5, window_seconds=0.05)
    for caller in range(100):
        window.allow(str(caller))

    time.sleep(0.06)
    window.allow("someone-else")

    assert len(window._hits) == 1
