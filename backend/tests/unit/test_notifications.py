"""What the platform writes, and what it is careful not to write down.

A reset link is a credential for the two hours it lives. Where it may appear is a short list:
the letter, and — on a stand with no mail server — the log, because otherwise the reset path
cannot be walked locally at all.
"""

import logging

import pytest

from app.core.config import Settings, get_settings
from app.core.mail import Letter
from app.services.notifications import deliver, password_reset_letter

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


async def test_a_stand_with_no_mail_server_logs_the_letter(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Without this the reset path cannot be walked locally at all."""
    letter = Letter(to="buyer@x.com", subject="x", body=f"link with {TOKEN}")

    with caplog.at_level(logging.INFO):
        await deliver(_settings(smtp_host=None, app_env="local"), letter)

    assert TOKEN in caplog.text


async def test_outside_local_nothing_is_written_down(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A secret in a production log is a leak, and a missing transport is a thing to report
    rather than a thing to work around."""
    letter = Letter(to="buyer@x.com", subject="x", body=f"link with {TOKEN}")

    with caplog.at_level(logging.INFO):
        await deliver(_settings(smtp_host=None, app_env="production"), letter)

    assert TOKEN not in caplog.text
    assert "no mail transport configured" in caplog.text
