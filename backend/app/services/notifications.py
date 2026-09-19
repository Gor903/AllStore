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
