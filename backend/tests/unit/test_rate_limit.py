"""The two shapes of allowance, and why they are two.

`SlidingWindow` refuses, and is keyed on where a request came from. `GraduatedDelay` slows
down, and is keyed on which account is being guessed at — a refusal keyed on somebody's email
would be a way to lock that person out using nothing but their address.
"""

import time

from app.core.rate_limit import GraduatedDelay, SlidingWindow


def test_the_allowance_is_spent_and_then_refused() -> None:
    window = SlidingWindow(limit=3, window_seconds=60.0)

    assert [window.check("a").allowed for _ in range(4)] == [True, True, True, False]


def test_keys_do_not_share_an_allowance() -> None:
    """Otherwise one noisy address would spend everybody else's attempts."""
    window = SlidingWindow(limit=1, window_seconds=60.0)

    assert window.check("a").allowed is True
    assert window.check("b").allowed is True
    assert window.check("a").allowed is False


def test_a_refusal_says_when_to_come_back() -> None:
    """A `Retry-After` of zero reads as an invitation rather than a limit."""
    window = SlidingWindow(limit=1, window_seconds=60.0)
    window.check("a")

    refused = window.check("a")

    assert refused.allowed is False
    assert 1 <= refused.retry_after_seconds <= 60


def test_an_allowance_comes_back_once_the_window_passes() -> None:
    window = SlidingWindow(limit=1, window_seconds=0.01)
    window.check("a")

    # the window is a fifth of the wait, so this is time passing rather than a race
    time.sleep(0.05)

    assert window.check("a").allowed is True


def test_idle_keys_are_forgotten() -> None:
    """A stream of distinct addresses must grow the table for one window, not for the life
    of the process."""
    window = SlidingWindow(limit=5, window_seconds=0.01)
    for index in range(50):
        window.check(f"address-{index}")

    time.sleep(0.05)
    window.check("somebody-else")

    assert len(window._hits) == 1


def test_the_first_attempts_cost_nothing() -> None:
    """Mistyping your own password twice is the ordinary case, not an attack."""
    delay = GraduatedDelay(free_attempts=3, window_seconds=60.0, step_seconds=0.5, cap_seconds=8.0)

    assert [delay.delay_for("a") for _ in range(3)] == [0.0, 0.0, 0.0]


def test_the_wait_doubles_and_then_stops_growing() -> None:
    delay = GraduatedDelay(free_attempts=1, window_seconds=60.0, step_seconds=1.0, cap_seconds=4.0)
    delay.delay_for("a")

    assert [delay.delay_for("a") for _ in range(5)] == [1.0, 2.0, 4.0, 4.0, 4.0]


def test_proving_the_account_is_yours_clears_what_came_before() -> None:
    """The owner who finally remembers their password should not keep paying for the guesses
    somebody else made at their address."""
    delay = GraduatedDelay(free_attempts=1, window_seconds=60.0, step_seconds=1.0, cap_seconds=8.0)
    for _ in range(4):
        delay.delay_for("a")

    delay.forget("a")

    assert delay.delay_for("a") == 0.0


def test_one_account_being_guessed_at_does_not_slow_another() -> None:
    delay = GraduatedDelay(free_attempts=1, window_seconds=60.0, step_seconds=1.0, cap_seconds=8.0)
    for _ in range(4):
        delay.delay_for("a")

    assert delay.delay_for("b") == 0.0
