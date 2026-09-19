import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_missing_required_settings_fail_fast(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("SECRET_KEY", "DATABASE_URL", "S3_BUCKET"):
        monkeypatch.delenv(name, raising=False)

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_cors_origins_accept_comma_separated(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CORS_ORIGINS", "http://localhost:3000, http://allstore.localhost")

    settings = Settings(_env_file=None)

    assert settings.cors_origins == ["http://localhost:3000", "http://allstore.localhost"]


def test_secrets_are_not_exposed_in_repr() -> None:
    settings = Settings(_env_file=None)

    assert "test-secret-not-for-real-use" not in repr(settings)


def test_short_secret_key_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    """HS256 signs with this key — a short one weakens every access token."""
    monkeypatch.setenv("SECRET_KEY", "too-short")

    with pytest.raises(ValidationError):
        Settings(_env_file=None)
