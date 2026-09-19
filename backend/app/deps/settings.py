from app.core.config import Settings, get_settings


def settings_dep() -> Settings:
    """Indirection so tests can override settings through FastAPI dependency_overrides."""
    return get_settings()
