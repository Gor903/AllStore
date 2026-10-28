import logging

import pytest

from app.core.config import get_settings
from app.services.notifications import (
    send_password_reset_email,
)


async def test_local_stub_logs_the_token(caplog: pytest.LogCaptureFixture) -> None:
    """Without the token in the log a local password reset cannot be completed."""
    with caplog.at_level(logging.INFO):
        await send_password_reset_email("buyer@example.com", "reset-token-value")

    assert "reset-token-value" in caplog.text


async def test_outside_local_the_token_is_not_logged(
    caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A secret in production logs is a leak — there the stub only reports the gap."""
    monkeypatch.setenv("APP_ENV", "production")
    get_settings.cache_clear()

    try:
        with caplog.at_level(logging.INFO):
            await send_password_reset_email("buyer@example.com", "reset-token-value")
    finally:
        get_settings.cache_clear()

    assert "reset-token-value" not in caplog.text
    assert "no email provider is configured" in caplog.text
