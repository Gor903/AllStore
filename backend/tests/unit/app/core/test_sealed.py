"""Short-lived state the server writes and the browser carries back.

Every property this module claims is a defence against something specific, so each one is
tested as an attack rather than as a feature:

- **signed**, or a visitor could write down which account they are halfway into signing in as;
- **base64url**, or the browser quotes or truncates a value containing the commas, quotes and
  braces JSON is made of — a bug this codebase has already had;
- **dated inside the payload**, because a signature does not expire, `Max-Age` is a request the
  browser may decline, and somebody replaying a cookie is not using a browser at all.

A value that fails any of these comes back as nothing. Nothing is not an error to explain: the
value is somebody else's or ours from another day, and either way the answer is to start again.
"""

import base64
import json

import pytest
from pydantic import SecretStr

from app.core.config import Settings, get_settings
from app.core.sealed import seal, unseal

AN_HOUR = 3600
PAYLOAD = {"user_id": "7", "purpose": "totp"}


def _settings(secret: str = "a" * 32) -> Settings:
    return get_settings().model_copy(update={"secret_key": SecretStr(secret)})


def test_what_was_written_comes_back() -> None:
    settings = _settings()

    read = unseal(settings, seal(settings, PAYLOAD), max_age_seconds=AN_HOUR)

    assert read is not None
    assert read["user_id"] == "7"
    assert read["purpose"] == "totp"


def test_the_value_survives_a_cookie_jar() -> None:
    """A cookie value may not contain a comma, a quote or a brace. Left raw, the browser
    quotes or truncates it and the round trip is lost."""
    sealed = seal(_settings(), PAYLOAD)

    assert all(character not in sealed for character in ',;"{}= ')


def test_a_payload_somebody_edited_comes_back_as_nothing() -> None:
    """The point of the signature: the caller holds the cookie and must not be able to write
    one. Without this, saying "I am halfway into signing in as the administrator" is free."""
    settings = _settings()
    signature = seal(settings, PAYLOAD).split(".", 1)[0]
    forged = json.dumps({"user_id": "1", "purpose": "totp", "iat": "9999999999"})
    tampered = base64.urlsafe_b64encode(forged.encode()).decode().rstrip("=")

    assert unseal(settings, f"{signature}.{tampered}", max_age_seconds=AN_HOUR) is None


def test_a_value_sealed_with_another_key_comes_back_as_nothing() -> None:
    """Which is also what makes rotating the secret end every half-finished sign-in."""
    sealed = seal(_settings("a" * 32), PAYLOAD)

    assert unseal(_settings("b" * 32), sealed, max_age_seconds=AN_HOUR) is None


@pytest.mark.parametrize(
    "sealed",
    [
        None,  # no cookie at all
        "",  # a cookie the browser sent empty
        "nodot",  # not this shape
        "deadbeef.notbase64!!",  # a signature over something unreadable
        "deadbeef." + base64.urlsafe_b64encode(b"not json").decode().rstrip("="),
    ],
)
def test_anything_that_is_not_ours_comes_back_as_nothing(sealed: str | None) -> None:
    assert unseal(_settings(), sealed, max_age_seconds=AN_HOUR) is None


def test_a_value_with_no_date_in_it_comes_back_as_nothing() -> None:
    """Even correctly signed: without `iat` there is no answer to "how old is this", and the
    safe reading of "unknown age" is "too old"."""
    settings = _settings()
    body = base64.urlsafe_b64encode(json.dumps({"user_id": "7"}).encode()).decode().rstrip("=")
    # signed the same way the module signs, so only the missing date can be what fails
    signature = seal(settings, {}).split(".", 1)[0]
    undated = f"{signature}.{body}"

    assert unseal(settings, undated, max_age_seconds=AN_HOUR) is None


def test_a_value_older_than_it_may_be_comes_back_as_nothing() -> None:
    """The age is checked against the time inside the signed payload, not against a `Max-Age`
    the browser was asked to honour: somebody replaying this is not using a browser."""
    settings = _settings()
    sealed = seal(settings, PAYLOAD, now=1_000_000)

    assert unseal(settings, sealed, max_age_seconds=AN_HOUR, now=1_000_000 + AN_HOUR + 1) is None


def test_a_value_within_its_age_is_still_read() -> None:
    settings = _settings()
    sealed = seal(settings, PAYLOAD, now=1_000_000)

    assert unseal(settings, sealed, max_age_seconds=AN_HOUR, now=1_000_000 + AN_HOUR) is not None


def test_the_same_payload_sealed_twice_in_a_second_is_the_same_value() -> None:
    """There is no nonce, and there is no need for one: this carries no secret of its own, it
    only says which half-finished sign-in a browser is in the middle of."""
    settings = _settings()

    assert seal(settings, PAYLOAD, now=1_000_000) == seal(settings, PAYLOAD, now=1_000_000)


def test_the_date_travels_inside_rather_than_beside_the_payload() -> None:
    """Beside it, it would be a field the caller can edit — and a signature over the rest."""
    settings = _settings()

    sealed = seal(settings, PAYLOAD, now=1_000_000)

    read = unseal(settings, sealed, max_age_seconds=AN_HOUR, now=1_000_000)

    assert read is not None
    assert read["iat"] == "1000000"
