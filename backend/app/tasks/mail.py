"""Sending one letter, with the right to try again.

The arguments are three strings rather than a `Letter`, because a task's arguments travel
through the broker as JSON and have to survive the round trip without the class that made
them. The letter is rebuilt on the other side.

Nothing here decides anything. Whether to write to somebody, and what to say, was settled by
the request that queued this — see `services/notifications.py`.
"""

import smtplib
import ssl

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.mail import Letter, deliver_now
from app.worker import celery_app, enqueue

logger = get_logger(__name__)

# What is worth trying again: a mail server that was busy, a connection that dropped, a TLS
# handshake that failed. All of them are "later, probably yes". A rejected recipient is not
# in this list and must not be — retrying it five times would be five identical refusals.
TRANSIENT = (smtplib.SMTPServerDisconnected, smtplib.SMTPConnectError, ssl.SSLError, OSError)


@celery_app.task(
    name="allstore.mail.send",
    bind=True,
    autoretry_for=TRANSIENT,
    # Ten seconds before the first retry, doubling to half an hour. Deliberately not the
    # library default of one second: that schedule is spent in half a minute, which is shorter
    # than most outages and would turn "the mail server blinked" back into "the letter is
    # gone" — the thing the queue exists to prevent. Eight tries on this curve keep asking for
    # the better part of an hour.
    retry_backoff=10,
    retry_backoff_max=1800,
    # without jitter every letter queued in the same minute retries in the same instant
    retry_jitter=True,
    max_retries=get_settings().mail_task_max_retries,
)
def send_letter(self: object, to: str, subject: str, body: str) -> None:
    """Hands one letter to the transport.

    When the tries run out the failure is logged with its traceback by Celery, and that line
    is the record of a letter nobody got — there is no further place to escalate to.
    """
    settings = get_settings()
    try:
        deliver_now(settings, Letter(to=to, subject=subject, body=body))
    except smtplib.SMTPRecipientsRefused:
        # Not retried, and not raised either: the address does not exist or will not have us,
        # and another eight attempts are another eight refusals. The log is the whole answer:
        # there is nobody left in the request to tell.
        logger.warning("the recipient %s was refused; not retrying", to)


def queue(letter: Letter) -> bool:
    """Puts one letter on the queue, and says whether it got there.

    The expiry belongs here rather than at the call site: it is a property of the letter —
    all of these are worth sending now and none of them in two days — and spelling it out ten
    times would be ten places for it to drift.
    """
    return enqueue(
        send_letter,
        letter.to,
        letter.subject,
        letter.body,
        expires=get_settings().mail_task_expires_seconds,
    )
