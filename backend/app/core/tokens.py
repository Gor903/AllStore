import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt

from app.core.config import Settings

ALGORITHM = "HS256"
TOKEN_TYPE_ACCESS = "access"  # noqa: S105  # a claim value, not a credential


class InvalidAccessToken(Exception):
    """Raised when an access token is missing, malformed, expired or not ours."""


@dataclass(frozen=True)
class AccessTokenPayload:
    user_id: uuid.UUID
    role: str


def create_access_token(settings: Settings, user_id: uuid.UUID, role: str) -> str:
    now = datetime.now(UTC)
    claims = {
        "sub": str(user_id),
        "role": role,
        "typ": TOKEN_TYPE_ACCESS,
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_ttl_minutes),
    }
    return jwt.encode(claims, settings.secret_key.get_secret_value(), algorithm=ALGORITHM)


def decode_access_token(settings: Settings, token: str) -> AccessTokenPayload:
    try:
        claims = jwt.decode(
            token,
            settings.secret_key.get_secret_value(),
            algorithms=[ALGORITHM],
            options={"require": ["exp", "sub"]},
        )
    except jwt.PyJWTError as exc:
        raise InvalidAccessToken(str(exc)) from exc

    # a refresh token must never be accepted where an access token is expected
    if claims.get("typ") != TOKEN_TYPE_ACCESS:
        raise InvalidAccessToken("unexpected token type")
    try:
        user_id = uuid.UUID(str(claims["sub"]))
    except ValueError as exc:
        raise InvalidAccessToken("subject is not a user id") from exc
    role = claims.get("role")
    if not isinstance(role, str):
        raise InvalidAccessToken("role claim is missing")
    return AccessTokenPayload(user_id=user_id, role=role)
