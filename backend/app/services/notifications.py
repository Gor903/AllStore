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


def email_confirmation_letter(
    settings: Settings, email: str, token: str, *, moving: bool
) -> Letter:
    """Asks an address to answer for itself.

    The wording differs between confirming what an account registered with and confirming a
    new address it wants to move to, because what the reader should do if they did not ask
    for it differs: in the first case ignore it, in the second somebody may be trying to take
    an account over and the owner of the old address is being told so separately.
    """
    link = f"{settings.public_url}/email/confirm?token={token}"
    hours = settings.email_verification_ttl_hours
    reason = (
        "Кто-то указал этот адрес как новый для аккаунта на AllStore.am."
        if moving
        else "Подтвердите адрес, указанный при регистрации на AllStore.am."
    )
    tail = (
        "Если это были не вы — не переходите по ссылке и смените пароль на старом адресе."
        if moving
        else "Если вы не регистрировались — просто не переходите по ссылке."
    )
    return Letter(
        to=email,
        subject="Подтверждение адреса — AllStore.am",
        body=f"{reason}\n\nЧтобы подтвердить:\n{link}\n\nСсылка действует {hours} ч.\n\n{tail}\n",
    )


def email_change_notice_letter(settings: Settings, old_email: str, new_email: str) -> Letter:
    """Tells the address being left behind that it is being left behind.

    This is the letter that matters most and the one nobody asks for. Somebody who has taken
    an account over will change the address; the only person who can notice is whoever still
    reads the old one, and they can only notice if they are told.
    """
    return Letter(
        to=old_email,
        subject="Запрошена смена адреса — AllStore.am",
        body=(
            f"Для вашего аккаунта на AllStore.am запрошена смена адреса на {new_email}.\n\n"
            "Пока новый адрес не подтверждён, вход по старому продолжает работать.\n\n"
            "Если это были не вы — немедленно смените пароль: "
            f"{settings.public_url}/password/forgot\n"
        ),
    )


def registration_attempt_letter(settings: Settings, email: str) -> Letter:
    """Goes to whoever already owns an address somebody just tried to register with.

    The form answered them the same way it answers a real registration, so this letter is the
    only thing that happens differently — and it is the half that matters, because the person
    it concerns is the owner, not the one who typed it.
    """
    return Letter(
        to=email,
        subject="Попытка регистрации — AllStore.am",
        body=(
            "Кто-то попытался зарегистрироваться на AllStore.am с этим адресом, "
            "но аккаунт на нём уже есть.\n\n"
            f"Если это были вы — просто войдите: {settings.public_url}/login\n"
            f"Забыли пароль: {settings.public_url}/password/forgot\n\n"
            "Если это были не вы — делать ничего не нужно, ваш аккаунт не затронут.\n"
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
