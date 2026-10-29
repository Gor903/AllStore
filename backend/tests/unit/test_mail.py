"""Putting a letter on the wire — the part that can be checked without a mail server.

Delivery itself cannot be tested here and is not pretended to be: what is checked is the
shape of what would be sent and, more importantly, that a mail server which is down or
unreachable cannot take anything else down with it.
"""

import smtplib

import pytest

from app.core import mail
from app.core.config import Settings, get_settings
from app.core.mail import Letter, compose, send

LETTER = Letter(to="buyer@example.com", subject="Тема", body="Тело письма")


def _settings(**overrides: object) -> Settings:
    return get_settings().model_copy(update=overrides)


def test_the_envelope_says_who_it_is_from_in_a_way_a_person_can_read() -> None:
    """Checked in parts rather than against one exact string: a display name with a dot in it
    comes back quoted, because that is what the standard asks for."""
    message = compose(
        _settings(mail_from="noreply@allstore.am", mail_from_name="AllStore.am"), LETTER
    )

    assert "AllStore.am" in str(message["From"])
    assert "<noreply@allstore.am>" in str(message["From"])
    assert message["To"] == "buyer@example.com"
    assert message["Subject"] == "Тема"
    assert "Тело письма" in message.get_content()


async def test_no_transport_means_no_letter_and_no_error() -> None:
    """A supported state, not a failure: the stand has no mail server and does not need one."""
    await send(_settings(smtp_host=None), LETTER)


async def test_a_mail_server_that_refuses_does_not_take_the_request_with_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """This runs after the answer has gone out, so there is nobody left to tell. Raising here
    would turn somebody else's outage into our own."""

    def _refuse(*args: object, **kwargs: object) -> None:
        raise smtplib.SMTPConnectError(421, "go away")

    monkeypatch.setattr(mail, "_deliver", _refuse)

    await send(_settings(smtp_host="smtp.example.com"), LETTER)


async def test_an_unreachable_host_is_survivable_too(monkeypatch: pytest.MonkeyPatch) -> None:
    """A name that does not resolve raises OSError rather than an SMTP error, and the two
    have to be caught together or the quieter one gets through."""

    def _unreachable(*args: object, **kwargs: object) -> None:
        raise OSError("name or service not known")

    monkeypatch.setattr(mail, "_deliver", _unreachable)

    await send(_settings(smtp_host="nowhere.invalid"), LETTER)
