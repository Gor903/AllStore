from argon2 import PasswordHasher

from app.core.security import (
    generate_token,
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
