import hashlib
import secrets
from functools import lru_cache

import anyio
import anyio.to_thread
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


@lru_cache
def _hashing_slots() -> anyio.CapacityLimiter:
    """How many passwords may be hashed at the same time.

    argon2id is deliberately expensive — 19 MiB and two passes per call — and that cost is the
    whole protection. Two things follow. Run on the event loop it stops the entire application
    rather than the one login that paid for it, so every call goes to a thread. Run in a
    threadpool with no ceiling it becomes a way to ask the machine for all of its memory at
    once, so the threads are counted. Both failures arrive together, under exactly the flood
    the allowances in deps/rate_limit.py exist to make expensive.
    """
    return anyio.CapacityLimiter(get_settings().argon2_max_parallel)


async def hash_password_in_thread(raw_password: str) -> str:
    return await anyio.to_thread.run_sync(hash_password, raw_password, limiter=_hashing_slots())


async def verify_password_in_thread(raw_password: str, password_hash: str) -> bool:
    return await anyio.to_thread.run_sync(
        verify_password, raw_password, password_hash, limiter=_hashing_slots()
    )


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
