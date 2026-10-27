from app.core.logging import get_logger

logger = get_logger(__name__)


async def send_password_reset_email(email: str, token: str) -> None:
    """Stub until the email provider is chosen (ADR 5, stage 8).

    The token is logged deliberately: without it local password reset cannot be tested.
    This is why the stub refuses to run outside a local environment.
    """
    from app.core.config import get_settings

    if not get_settings().is_local:
        logger.error("password reset requested for %s but no email provider is configured", email)
        return
    logger.info("password reset for %s, token=%s", email, token)


async def send_moderator_invitation_email(email: str, token: str) -> None:
    """Stub until the email provider is chosen (ADR 5, stage 8).

    Outside a local environment the token is deliberately not logged: an invitation is a
    credential, and a log line is not where credentials go. The administrator copies the link
    from the answer to the request that created it — once — until mail is wired up.
    """
    from app.core.config import get_settings

    if not get_settings().is_local:
        logger.info("moderator invitation issued for %s; deliver the link by hand", email)
        return
    logger.info("moderator invitation for %s, token=%s", email, token)
