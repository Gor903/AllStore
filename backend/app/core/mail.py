"""Putting a letter on the wire.

Plain `smtplib` in a thread rather than an async client, for the same reason argon2 went to a
thread: the work blocks, and blocking the event loop stops the whole application rather than
the one request that asked for it. There is no async SMTP client in the dependency set and
nothing here needs one — a letter is sent in the background, so nobody is waiting on it.

The transport is deliberately the only thing this module knows about. What to say, to whom and
why lives in `services/notifications.py`; swapping Gmail for a hosted provider later is a
change of four settings and nothing else.

Unset `SMTP_HOST` means no transport at all, which is a supported state and not an error: the
local stand logs its letters instead, and the suite does not need a mail server to run.
"""

import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage

import anyio
import anyio.to_thread

from app.core.config import Settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# One at a time. A letter takes a TLS handshake and a round trip, and nothing here is urgent
# enough to hold several connections open to somebody else's mail server.
_sending = anyio.CapacityLimiter(1)


@dataclass(frozen=True)
class Letter:
    to: str
    subject: str
    body: str


def compose(settings: Settings, letter: Letter) -> EmailMessage:
    """Public so a test can look at the envelope without a mail server to send it to."""
    message = EmailMessage()
    message["From"] = f"{settings.mail_from_name} <{settings.mail_from}>"
    message["To"] = letter.to
    message["Subject"] = letter.subject
    message.set_content(letter.body)
    return message


def _deliver(settings: Settings, message: EmailMessage) -> None:
    """The blocking half, run in a thread.

    `starttls` rather than an implicit TLS port because that is what port 587 is, and 587 is
    what every provider in the running has asked for.
    """
    with smtplib.SMTP(
        settings.smtp_host or "", settings.smtp_port, timeout=settings.smtp_timeout
    ) as server:
        if settings.smtp_starttls:
            server.starttls(context=ssl.create_default_context())
        if settings.smtp_user and settings.smtp_password is not None:
            server.login(settings.smtp_user, settings.smtp_password.get_secret_value())
        server.send_message(message)


async def send(settings: Settings, letter: Letter) -> None:
    """Sends it, or writes down that it could not.

    Never raises. This is called from a background task after the answer has already gone out,
    so there is nobody left to tell — and a letter that failed to send must not be able to take
    anything else down with it. What it can do is leave a line in the log saying so.
    """
    if not settings.smtp_host:
        logger.info("no mail transport configured, letter to %s not sent", letter.to)
        return
    try:
        await anyio.to_thread.run_sync(
            _deliver, settings, compose(settings, letter), limiter=_sending
        )
    except (smtplib.SMTPException, ssl.SSLError, OSError):
        # the address is logged, the body is not: a letter can carry a reset link
        logger.exception("could not send the letter to %s", letter.to)
