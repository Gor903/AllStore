"""What the platform writes to people, and why each letter exists.

Every one of these is transactional: it answers something the person just did. There is no
marketing here and there should not be — a list that carries both is a list people unsubscribe
from, and the letters below are the ones they cannot afford to miss.

Composing is separated from sending (`core/mail.py`) so that a letter can be built inside a
request and put on the wire afterwards. That separation is not tidiness: `request_password_reset`
must take the same time for an address that exists and one that does not, and waiting on
somebody else's mail server inside the request would answer that question out loud.
"""

from app.core.config import Settings
from app.core.logging import get_logger
from app.core.mail import Letter, send

logger = get_logger(__name__)


def password_reset_letter(settings: Settings, email: str, token: str) -> Letter:
    """The link carries the token, which is why the reset page is served with
    `Referrer-Policy: no-referrer` — otherwise following any link from it would hand the token
    to whatever was linked to."""
    link = f"{settings.public_url}/password/reset?token={token}"
    hours = settings.password_reset_ttl_hours
    return Letter(
        to=email,
        subject="Восстановление пароля — AllStore.am",
        body=(
            "Кто-то запросил восстановление пароля для этого адреса на AllStore.am.\n\n"
            f"Чтобы задать новый пароль, перейдите по ссылке:\n{link}\n\n"
            f"Ссылка действует {hours} ч. и срабатывает один раз.\n\n"
            "Если вы этого не просили — ничего делать не нужно, пароль останется прежним.\n"
        ),
    )


async def deliver(settings: Settings, letter: Letter) -> None:
    """Called from a background task, after the answer has gone out.

    A separate name rather than exporting `send` directly: everything that writes to people
    goes through this module, so there is one place to look when somebody asks what the
    platform sends and one place to add a log, a queue or a suppression list later.
    """
    if not settings.smtp_host and settings.is_local:
        # the stand has no mail server and does not need one; the token is the only way to
        # walk the reset path locally, and the environment check is what keeps it local
        logger.info("letter to %s: %s", letter.to, letter.body)
        return
    await send(settings, letter)
