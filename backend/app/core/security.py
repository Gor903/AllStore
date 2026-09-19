import hashlib
import secrets
from functools import lru_cache

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from app.core.config import get_settings

MIN_PASSWORD_LENGTH = 10
MAX_PASSWORD_LENGTH = 128


@lru_cache
def get_password_hasher() -> PasswordHasher:
    settings = get_settings()
    return PasswordHasher(
        time_cost=settings.argon2_time_cost,
        memory_cost=settings.argon2_memory_cost,
        parallelism=settings.argon2_parallelism,
    )


def hash_password(raw_password: str) -> str:
    return get_password_hasher().hash(raw_password)


def verify_password(raw_password: str, password_hash: str) -> bool:
    try:
        return get_password_hasher().verify(password_hash, raw_password)
    except (VerificationError, InvalidHashError):
        return False


def password_needs_rehash(password_hash: str) -> bool:
    """Argon2 parameters grow over time — an old hash is upgraded on the next successful login."""
    try:
        return get_password_hasher().check_needs_rehash(password_hash)
    except InvalidHashError:
        return True


def generate_token() -> str:
    """Opaque token for refresh and password reset — the client sees it exactly once."""
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    """Tokens are stored as sha256: a database leak yields no usable tokens.

    Unlike passwords these need no stretching — the token is already random and long.
    """
    return hashlib.sha256(token.encode()).hexdigest()
