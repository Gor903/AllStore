"""One indirection, and the reason it exists.

The settings are read once per process and cached; a route that called `get_settings()`
directly would be a route no test can give different settings to. This dependency is the seam
`dependency_overrides` can reach — which is how the suite runs a route with a different base
domain, a different environment or no Redis at all without touching the environment of the
process it is running in.
"""

from app.core.config import Settings, get_settings
from app.deps.settings import settings_dep


def test_it_answers_with_the_settings_the_platform_is_running_on() -> None:
    assert settings_dep() is get_settings()


def test_the_settings_are_read_once_rather_than_per_request() -> None:
    """Parsing the environment on every call would be work done thousands of times for an
    answer that cannot change while the process lives."""
    assert settings_dep() is settings_dep()


def test_it_is_a_function_a_test_can_stand_in_for() -> None:
    """A route reading `get_settings()` by hand could not be given different settings; this
    one can, because FastAPI resolves it by identity."""
    assert callable(settings_dep)
    assert isinstance(settings_dep(), Settings)
