import threading

import pytest
from argon2 import PasswordHasher

from app.core import security
from app.core.config import get_settings
from app.core.security import (
    generate_token,
    get_password_hasher,
    hash_password,
    hash_token,
    password_needs_rehash,
    verify_password,
)


def test_hash_does_not_contain_the_password() -> None:
    password_hash = hash_password("correct horse battery staple")

    assert "correct horse battery staple" not in password_hash
    assert password_hash.startswith("$argon2id$")


def test_same_password_hashes_differently() -> None:
    assert hash_password("same-password") != hash_password("same-password")


def test_verify_accepts_the_right_password() -> None:
    password_hash = hash_password("s3cret-password")

    assert verify_password("s3cret-password", password_hash) is True


def test_verify_rejects_the_wrong_password() -> None:
    password_hash = hash_password("s3cret-password")

    assert verify_password("other-password", password_hash) is False


def test_verify_rejects_a_malformed_hash() -> None:
    assert verify_password("any-password", "not-a-hash") is False


def test_rehash_is_requested_for_weaker_parameters() -> None:
    weaker = PasswordHasher(time_cost=1, memory_cost=8, parallelism=1).hash("s3cret-password")

    assert password_needs_rehash(weaker) is True
    assert password_needs_rehash(hash_password("s3cret-password")) is False


def test_rehash_is_requested_for_a_malformed_hash() -> None:
    """A hash the library cannot parse must be replaced, not trusted."""
    assert password_needs_rehash("not-a-hash") is True


def test_generated_tokens_are_unique() -> None:
    tokens = {generate_token() for _ in range(100)}

    assert len(tokens) == 100


def test_token_hash_is_deterministic_and_hides_the_token() -> None:
    token = generate_token()

    digest = hash_token(token)

    assert digest == hash_token(token)
    assert len(digest) == 64
    assert token not in digest
    assert digest != hash_token(generate_token())


async def test_hashing_happens_off_the_event_loop(monkeypatch: pytest.MonkeyPatch) -> None:
    """argon2 costs 19 MiB and two passes, and on the loop that cost is paid by every request
    in flight rather than by the one login that asked for it."""
    ran_on: list[int] = []

    def _record(raw_password: str) -> str:
        ran_on.append(threading.get_ident())
        return "not-a-real-hash"

    monkeypatch.setattr(security, "hash_password", _record)

    await security.hash_password_in_thread("whatever")

    assert ran_on, "the hasher was never called"
    assert ran_on[0] != threading.get_ident()


async def test_verifying_happens_off_the_event_loop(monkeypatch: pytest.MonkeyPatch) -> None:
    ran_on: list[int] = []

    def _record(raw_password: str, password_hash: str) -> bool:
        ran_on.append(threading.get_ident())
        return True

    monkeypatch.setattr(security, "verify_password", _record)

    assert await security.verify_password_in_thread("whatever", "hash") is True
    assert ran_on[0] != threading.get_ident()


def test_hashing_is_capped_so_a_flood_cannot_ask_for_all_the_memory() -> None:
    """Unbounded threads at 19 MiB each is a way to request the machine, politely."""
    assert security._hashing_slots().total_tokens == get_settings().argon2_max_parallel


def test_the_same_password_from_two_keyboards_is_one_password() -> None:
    """An accented character can be one code point or two, and which one a device produces is
    not something anybody chooses or notices."""
    composed = "paéssword-1"
    decomposed = "paéssword-1"
    assert composed != decomposed

    stored = hash_password(composed)

    assert verify_password(decomposed, stored) is True


def test_a_password_chosen_before_normalisation_still_opens_its_account() -> None:
    """Its hash was made from whatever the keyboard produced, and nobody may be locked out by
    a change in how we fold characters."""
    decomposed = "paéssword-1"
    legacy = get_password_hasher().hash(decomposed)

    assert verify_password(decomposed, legacy) is True


def test_a_wrong_password_still_costs_exactly_one_hash(monkeypatch: pytest.MonkeyPatch) -> None:
    """The second attempt is for folded characters only. Paying it on every failure would
    double what a flood of wrong passwords costs the machine."""
    attempts = 0
    original = security._matches

    def counting(candidate: str, password_hash: str) -> bool:
        nonlocal attempts
        attempts += 1
        return original(candidate, password_hash)

    monkeypatch.setattr(security, "_matches", counting)

    assert (
        security.verify_password("plain-ascii-wrong", hash_password("plain-ascii-right")) is False
    )
    assert attempts == 1
