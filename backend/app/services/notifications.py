"""What the platform writes to people, and why each letter exists.

Every one of these is transactional: it answers something the person just did. There is no
marketing here and there should not be — a list that carries both is a list people unsubscribe
from, and the letters below are the ones they cannot afford to miss.

Composing is separated from sending (`core/mail.py`) so that a letter can be built inside a
request and put on the wire afterwards. That separation is not tidiness: `request_password_reset`
must take the same time for an address that exists and one that does not, and waiting on
somebody else's mail server inside the request would answer that question out loud.
"""

import asyncio

from app.core.config import Settings
from app.core.logging import get_logger
from app.core.mail import Letter, send
from app.tasks.mail import queue

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


def new_device_letter(
    settings: Settings, email: str, user_agent: str | None, ip: str | None
) -> Letter:
    """Tells somebody their account was opened somewhere new.

    The letter nobody asks for and the one that catches a stolen password: the thief has the
    credentials and the account, and the only thing they do not have is the inbox. What they
    cannot prevent is this arriving in it.

    Deliberately not sent on every sign-in. A letter for each of somebody's own daily logins
    is a letter they stop reading, and then the one that mattered goes unread too.
    """
    where = ", ".join(part for part in (user_agent, ip) if part) or "неизвестное устройство"
    return Letter(
        to=email,
        subject="Новый вход в аккаунт — AllStore.am",
        body=(
            f"В ваш аккаунт на AllStore.am вошли с нового устройства:\n{where}\n\n"
            f"Если это были вы — ничего делать не нужно.\n\n"
            "Если нет — завершите чужие сессии и смените пароль:\n"
            f"{settings.public_url}/devices\n"
            f"{settings.public_url}/password/forgot\n"
        ),
    )


def password_changed_letter(settings: Settings, email: str) -> Letter:
    """Somebody who did not change it is the only person this concerns, and the only way they
    find out in time."""
    return Letter(
        to=email,
        subject="Пароль изменён — AllStore.am",
        body=(
            "Пароль вашего аккаунта на AllStore.am был изменён, все сессии завершены.\n\n"
            "Если это были не вы — восстановите доступ немедленно:\n"
            f"{settings.public_url}/password/forgot\n"
        ),
    )


def google_link_letter(settings: Settings, email: str, *, attached: bool) -> Letter:
    """A way into the account was added, or taken away.

    Both directions are worth a letter and for opposite reasons. An attachment nobody asked
    for means somebody else can now open the account without knowing the password — the one
    change an intruder makes that leaves the password working, so the owner notices nothing.
    A detachment nobody asked for is how an owner is locked out of their own way in.
    """
    what = (
        "К вашему аккаунту на AllStore.am привязан вход через Google."
        if attached
        else "От вашего аккаунта на AllStore.am отвязан вход через Google."
    )
    return Letter(
        to=email,
        subject="Способы входа изменились — AllStore.am",
        body=(
            f"{what}\n\n"
            "Если это были вы — ничего делать не нужно.\n\n"
            "Если нет — смените пароль и завершите чужие сессии:\n"
            f"{settings.public_url}/password/forgot\n"
            f"{settings.public_url}/devices\n"
        ),
    )


def deliver(settings: Settings, letter: Letter) -> None:
    """Puts the letter on the queue. Returns as soon as it is there, which is at once.

    Synchronous and safe to call from anywhere — an endpoint, a dependency, a startup hook.
    That is the point of the queue: the previous arrangement could only send from an endpoint,
    because only an endpoint has `BackgroundTasks`, and so the one place that most needed to
    write to somebody — the dependency that notices a stolen session token — could not.

    Call it **after** the commit. A letter about something that was rolled back is a lie, and
    the worker is quite capable of sending it before the transaction ends.
    """
    if settings.is_local:
        # The stand's log is its inbox. The confirmation and reset links are read from there —
        # by a person walking the path and by the end-to-end run alike — and that stays true
        # once a real transport is configured: pointing the stand at somebody's mailbox must
        # not take away its only way of reading its own letters. Logged here rather than in
        # the worker so that the stand's letters stay in one log. The environment check is
        # what keeps a link that is a credential out of a production log.
        logger.info("letter to %s: %s", letter.to, letter.body)
    if queue(letter):
        return
    # The broker is down and the request it belongs to has already succeeded. Sending it here
    # loses the retries but keeps the letter, which is the better half of a bad choice.
    _send_without_a_queue(settings, letter)


def _send_without_a_queue(settings: Settings, letter: Letter) -> None:
    """The fallback, when there is no queue to put the letter on.

    Inside a request there is a running loop, and the send is started on it and let go: it
    takes a TLS handshake and a round trip, and blocking the loop for that would punish every
    other request for one letter. The reference is kept because an unreferenced task may be
    collected before it runs.

    Outside a loop — a script, the worker itself — there is nobody to punish, so it simply
    runs. `send` never raises, so in both cases the failure ends in the log and nowhere else.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        asyncio.run(send(settings, letter))
        return
    task = asyncio.ensure_future(send(settings, letter))
    _unqueued.add(task)
    task.add_done_callback(_unqueued.discard)


# Started and let go, but not forgotten: asyncio keeps only a weak reference to a running
# task, so one nobody holds can be collected mid-flight.
_unqueued: set[asyncio.Task[None]] = set()
