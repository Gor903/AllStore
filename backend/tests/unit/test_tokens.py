import uuid
from datetime import UTC, datetime, timedelta

import jwt
import pytest

from app.core.config import Settings, get_settings
from app.core.tokens import ALGORITHM, InvalidAccessToken, create_access_token, decode_access_token


@pytest.fixture
def settings() -> Settings:
    return get_settings()


def test_access_token_round_trips(settings: Settings) -> None:
    user_id = uuid.uuid4()

    payload = decode_access_token(settings, create_access_token(settings, user_id, "buyer"))

    assert payload.user_id == user_id
    assert payload.role == "buyer"


def test_token_signed_with_another_secret_is_refused(settings: Settings) -> None:
    foreign = jwt.encode(
        {
            "sub": str(uuid.uuid4()),
            "typ": "access",
            "exp": datetime.now(UTC) + timedelta(minutes=5),
        },
        "someone-elses-secret-that-is-also-long-enough",
        algorithm=ALGORITHM,
    )

    with pytest.raises(InvalidAccessToken):
        decode_access_token(settings, foreign)


def test_expired_token_is_refused(settings: Settings) -> None:
    expired = jwt.encode(
        {
            "sub": str(uuid.uuid4()),
            "role": "buyer",
            "typ": "access",
            "exp": datetime.now(UTC) - timedelta(seconds=1),
        },
        settings.secret_key.get_secret_value(),
        algorithm=ALGORITHM,
    )

    with pytest.raises(InvalidAccessToken):
        decode_access_token(settings, expired)


def test_token_of_another_type_is_refused(settings: Settings) -> None:
    """Without the type check a refresh token would pass as an access token."""
    other_type = jwt.encode(
        {
            "sub": str(uuid.uuid4()),
            "role": "buyer",
            "typ": "refresh",
            "exp": datetime.now(UTC) + timedelta(minutes=5),
        },
        settings.secret_key.get_secret_value(),
        algorithm=ALGORITHM,
    )

    with pytest.raises(InvalidAccessToken):
        decode_access_token(settings, other_type)


def test_token_without_a_user_id_is_refused(settings: Settings) -> None:
    broken = jwt.encode(
        {
            "sub": "not-a-uuid",
            "role": "buyer",
            "typ": "access",
            "exp": datetime.now(UTC) + timedelta(minutes=5),
        },
        settings.secret_key.get_secret_value(),
        algorithm=ALGORITHM,
    )

    with pytest.raises(InvalidAccessToken):
        decode_access_token(settings, broken)


def test_token_without_a_role_is_refused(settings: Settings) -> None:
    roleless = jwt.encode(
        {
            "sub": str(uuid.uuid4()),
            "typ": "access",
            "exp": datetime.now(UTC) + timedelta(minutes=5),
        },
        settings.secret_key.get_secret_value(),
        algorithm=ALGORITHM,
    )

    with pytest.raises(InvalidAccessToken):
        decode_access_token(settings, roleless)


def test_garbage_is_refused(settings: Settings) -> None:
    with pytest.raises(InvalidAccessToken):
        decode_access_token(settings, "not.a.token")
