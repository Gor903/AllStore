"""The algorithm, checked against the numbers in the specification.

This is the part of a home-grown implementation that has to be right: an authenticator
application computes codes from the same secret with its own code, and if ours disagrees by
one bit, every code anybody types is wrong and nobody can tell why. The vectors below are
from RFC 6238, appendix B — the published answers for a known secret at known times.
"""

import base64

import pytest

from app.core.totp import (
    DIGITS,
    STEP_SECONDS,
    code_for,
    generate_secret,
    matching_step,
    provisioning_uri,
    step_at,
)

# the secret the RFC uses: ASCII "12345678901234567890", in the base32 an authenticator wants
RFC_SECRET = base64.b32encode(b"12345678901234567890").decode().rstrip("=")

# (unix time, the last six digits of the eight the RFC publishes for SHA-1)
RFC_VECTORS = [
    (59, "287082"),
    (1111111109, "081804"),
    (1111111111, "050471"),
    (1234567890, "005924"),
    (2000000000, "279037"),
    (20000000000, "353130"),
]


@pytest.mark.parametrize(("moment", "expected"), RFC_VECTORS)
def test_the_codes_are_the_ones_the_specification_publishes(moment: int, expected: str) -> None:
    assert code_for(RFC_SECRET, step_at(moment)) == expected


def test_a_step_lasts_thirty_seconds() -> None:
    """Not a preference: it is what every authenticator assumes when the link does not say."""
    assert step_at(0) == step_at(STEP_SECONDS - 1)
    assert step_at(STEP_SECONDS) == step_at(0) + 1


def test_a_code_is_six_digits_with_the_leading_zeros_kept() -> None:
    """Dropped, a code starting with a zero is five digits and never matches."""
    codes = [code_for(generate_secret(), step) for step in range(500)]

    assert all(len(code) == DIGITS and code.isdigit() for code in codes)


def test_the_code_from_now_matches() -> None:
    secret = generate_secret()
    moment = 1_700_000_000.0

    assert matching_step(secret, code_for(secret, step_at(moment)), moment) == step_at(moment)


def test_a_clock_that_is_a_little_out_still_works() -> None:
    """A telephone whose clock drifts by a few seconds is the ordinary case, not an attack."""
    secret = generate_secret()
    moment = 1_700_000_000.0
    here = step_at(moment)

    assert matching_step(secret, code_for(secret, here - 1), moment) == here - 1
    assert matching_step(secret, code_for(secret, here + 1), moment) == here + 1


def test_a_clock_that_is_a_long_way_out_does_not() -> None:
    """Widening the window widens the guessing window by exactly as much."""
    secret = generate_secret()
    moment = 1_700_000_000.0

    assert matching_step(secret, code_for(secret, step_at(moment) - 5), moment) is None


def test_a_step_that_was_already_spent_is_refused() -> None:
    """Without this a code read over somebody's shoulder works a second time."""
    secret = generate_secret()
    moment = 1_700_000_000.0
    here = step_at(moment)

    assert matching_step(secret, code_for(secret, here), moment, after=here) is None
    assert matching_step(secret, code_for(secret, here + 1), moment, after=here) == here + 1


def test_something_that_is_not_a_code_is_not_a_code() -> None:
    secret = generate_secret()

    assert matching_step(secret, "abcdef", 1_700_000_000.0) is None
    assert matching_step(secret, "12345", 1_700_000_000.0) is None
    assert matching_step(secret, "", 1_700_000_000.0) is None


def test_two_secrets_are_not_the_same_secret() -> None:
    assert len({generate_secret() for _ in range(100)}) == 100


def test_the_link_says_everything_an_application_needs() -> None:
    """An entry showing nothing but an address is one nobody can tell from their other six,
    and an algorithm left unsaid is one the application guesses."""
    uri = provisioning_uri("ABCDEFGH", "person@example.com", "AllStore.am")

    assert uri.startswith("otpauth://totp/AllStore.am%3Aperson%40example.com?")
    assert "secret=ABCDEFGH" in uri
    assert "issuer=AllStore.am" in uri
    assert "algorithm=SHA1" in uri
    assert "digits=6" in uri
    assert "period=30" in uri
