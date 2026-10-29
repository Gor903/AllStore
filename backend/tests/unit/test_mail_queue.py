"""The queue a letter travels on, and what happens when it is not there.

The point of moving mail off `BackgroundTasks` was never speed — a letter was already sent
after the response. It was that a send which fails had nobody to try again, and that anything
which is not an endpoint had no `BackgroundTasks` to put work on at all. Both of those are
what this file checks.
"""

import logging
import smtplib
import ssl

import pytest
from celery.exceptions import Retry

from app.core.config import Settings, get_settings
from app.core.mail import Letter
from app.services import notifications
from app.tasks.mail import TRANSIENT, send_letter
from app.worker import celery_app, enqueue, ping

LETTER = Letter(to="buyer@x.com", subject="Тема", body="тело письма")


def _settings(**overrides: object) -> Settings:
    return get_settings().model_copy(update=overrides)


def test_the_task_is_registered_under_a_name_that_outlives_the_function() -> None:
    """The name travels through the broker, so renaming the function must not strand the
    letters already queued under the old one."""
    assert send_letter.name == "allstore.mail.send"
    assert ping.name == "allstore.ping"
    assert {"allstore.mail.send", "allstore.ping"} <= set(celery_app.tasks)


def test_the_arguments_are_things_json_can_carry() -> None:
    """A `Letter` would have to be pickled, and a broker that carries pickled objects is a
    broker that runs whatever is written to it."""
    assert celery_app.conf.task_serializer == "json"
    assert celery_app.conf.accept_content == ["json"]


def test_a_mail_server_having_a_bad_day_is_asked_again(monkeypatch: pytest.MonkeyPatch) -> None:
    """This is the whole reason the queue exists: before it, this letter was simply gone."""

    def refuse(settings: Settings, letter: Letter) -> None:
        raise smtplib.SMTPServerDisconnected("not now")

    monkeypatch.setattr("app.tasks.mail.deliver_now", refuse)

    with pytest.raises(Retry):
        send_letter.apply(args=(LETTER.to, LETTER.subject, LETTER.body)).get()


def test_an_address_that_does_not_exist_is_not_asked_again(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Another eight attempts would be another eight identical refusals."""

    def refuse(settings: Settings, letter: Letter) -> None:
        raise smtplib.SMTPRecipientsRefused({LETTER.to: (550, b"no such user")})

    monkeypatch.setattr("app.tasks.mail.deliver_now", refuse)

    with caplog.at_level(logging.WARNING):
        result = send_letter.apply(args=(LETTER.to, LETTER.subject, LETTER.body))

    assert result.successful()
    assert "not retrying" in caplog.text


def test_only_the_failures_worth_repeating_are_repeated() -> None:
    """A refused recipient in this tuple would turn one wrong address into nine attempts."""
    assert smtplib.SMTPRecipientsRefused not in TRANSIENT
    assert ssl.SSLError in TRANSIENT


def test_a_letter_goes_through_the_queue(monkeypatch: pytest.MonkeyPatch) -> None:
    queued: list[Letter] = []

    def fake_queue(letter: Letter) -> bool:
        queued.append(letter)
        return True

    monkeypatch.setattr(notifications, "queue", fake_queue)

    notifications.deliver(_settings(app_env="production"), LETTER)

    assert queued == [LETTER]


def test_a_broker_that_is_down_does_not_lose_the_letter(monkeypatch: pytest.MonkeyPatch) -> None:
    """The request that queued this has already succeeded — the account exists, the password
    changed. A queue that is down must not become a failure the person sees, and must not
    quietly swallow the letter either."""
    sent: list[Letter] = []

    async def fake_send(settings: Settings, letter: Letter) -> None:
        sent.append(letter)

    monkeypatch.setattr(notifications, "queue", lambda letter: False)
    monkeypatch.setattr(notifications, "send", fake_send)

    notifications.deliver(_settings(app_env="production"), LETTER)

    assert sent == [LETTER]


def test_a_broker_that_refuses_is_reported_rather_than_raised(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """`enqueue` is called from endpoints that have already committed."""

    class Unreachable:
        name = "allstore.test"

        def apply_async(self, **options: object) -> None:
            raise OSError("no route to the broker")

    with caplog.at_level(logging.ERROR):
        assert enqueue(Unreachable()) is False

    assert "could not queue allstore.test" in caplog.text
