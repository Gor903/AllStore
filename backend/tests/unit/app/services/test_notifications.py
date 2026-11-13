"""What the platform writes, and what it is careful not to write down.

A reset link is a credential for the two hours it lives. Where it may appear is a short list:
the letter, and — on a stand with no mail server — the log, because otherwise the reset path
cannot be walked locally at all.
"""

import logging

import pytest

from app.core.config import Settings, get_settings
from app.core.mail import Letter
from app.services.notifications import (
    deliver,
    new_device_letter,
    password_reset_letter,
    staff_account_letter,
)

TOKEN = "reset-token-value"


def _settings(**overrides: object) -> Settings:
    return get_settings().model_copy(update=overrides)


def test_the_letter_carries_the_link_and_says_what_it_is_for() -> None:
    letter = password_reset_letter(_settings(site_url="https://allstore.am"), "buyer@x.com", TOKEN)

    assert letter.to == "buyer@x.com"
    assert f"https://allstore.am/password/reset?token={TOKEN}" in letter.body
    # somebody who did not ask has to be told they need do nothing
    assert "ничего делать не нужно" in letter.body


def test_the_link_knows_how_long_it_lives() -> None:
    """A link with no stated life is a link people sit on until it stops working."""
    letter = password_reset_letter(_settings(password_reset_ttl_hours=2), "buyer@x.com", TOKEN)

    assert "2 ч." in letter.body


def test_the_address_falls_back_to_the_domain_we_know() -> None:
    letter = password_reset_letter(
        _settings(site_url=None, base_domain="allstore.am"), "buyer@x.com", TOKEN
    )

    assert "https://allstore.am/password/reset" in letter.body


def test_a_letter_about_a_new_device_says_where_from() -> None:
    """A letter that only says "somebody signed in" leaves the reader with no way to tell
    whether it was their own phone."""
    letter = new_device_letter(_settings(), "buyer@x.com", "Firefox on Linux", "203.0.113.7")

    assert "Firefox on Linux" in letter.body
    assert "203.0.113.7" in letter.body


def test_a_device_that_said_nothing_about_itself_is_still_reported() -> None:
    """A proxy that strips the headers must not turn the letter into a blank."""
    letter = new_device_letter(_settings(), "buyer@x.com", None, None)

    assert "неизвестное устройство" in letter.body


@pytest.mark.parametrize(
    ("administrator", "expected"), [(True, "администратора"), (False, "модератора")]
)
def test_a_new_staff_account_is_announced_to_its_address(
    administrator: bool, expected: str
) -> None:
    """The reader did not ask for anything, so the letter has to say which seat was opened
    on their address and what to do if they were not expecting it."""
    letter = staff_account_letter(_settings(), "staff@x.com", administrator=administrator)

    assert letter.to == "staff@x.com"
    assert expected in letter.body
    assert "сообщите администратору" in letter.body


def test_the_handed_over_password_never_travels_by_letter() -> None:
    """A letter carrying it would turn one readable mailbox into a staff seat — which is the
    thing the temporary password exists to prevent."""
    letter = staff_account_letter(_settings(), "staff@x.com", administrator=False)

    assert "в письме его нет" in letter.body


def test_a_stand_with_no_mail_server_logs_the_letter(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Without this the reset path cannot be walked locally at all."""
    letter = Letter(to="buyer@x.com", subject="x", body=f"link with {TOKEN}")

    with caplog.at_level(logging.INFO):
        deliver(_settings(smtp_host=None, app_env="local"), letter)

    assert TOKEN in caplog.text


def test_outside_local_nothing_is_written_down(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A secret in a production log is a leak, and a missing transport is a thing to report
    rather than a thing to work around."""
    letter = Letter(to="buyer@x.com", subject="x", body=f"link with {TOKEN}")

    with caplog.at_level(logging.INFO):
        deliver(_settings(smtp_host=None, app_env="production"), letter)

    assert TOKEN not in caplog.text
    assert "no mail transport configured" in caplog.text
