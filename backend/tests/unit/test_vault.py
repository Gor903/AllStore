"""What a stored secret looks like, and what happens when it cannot be read back.

A TOTP secret has to be recoverable — the server computes codes from it — and "recoverable"
is not "plain in the table". A dump, a backup, a replica somebody was given access to: each
of those is a copy of every second factor on the platform unless this works.
"""

from app.core.config import Settings, get_settings
from app.core.vault import lock, unlock

SECRET = "JBSWY3DPEHPK3PXP"


def _settings(**overrides: object) -> Settings:
    return get_settings().model_copy(update=overrides)


def test_what_goes_in_comes_back() -> None:
    assert unlock(_settings(), lock(_settings(), SECRET)) == SECRET


def test_the_stored_form_does_not_contain_the_secret() -> None:
    assert SECRET not in lock(_settings(), SECRET)


def test_the_same_secret_stores_differently_every_time() -> None:
    """A fresh nonce each time, so two accounts with the same secret — or one account
    enrolling twice — do not have matching rows for anybody to notice."""
    assert lock(_settings(), SECRET) != lock(_settings(), SECRET)


def test_a_row_somebody_edited_is_refused_rather_than_decoded() -> None:
    """AES-GCM, so a changed byte is a failure and not a different secret."""
    stored = lock(_settings(), SECRET)
    tampered = stored[:-4] + ("AAAA" if not stored.endswith("AAAA") else "BBBB")

    assert unlock(_settings(), tampered) is None


def test_nonsense_is_refused_without_raising() -> None:
    """Callers treat `None` as "this factor cannot be used"; an exception here would come out
    of a sign-in as a 500."""
    assert unlock(_settings(), "not base64 at all !!") is None
    assert unlock(_settings(), "") is None


def test_a_different_key_cannot_read_it() -> None:
    """Rotating SECRET_KEY makes every stored value unreadable and everybody enrol again.
    That is the honest cost of one secret instead of a key service, and it is written down."""
    from pydantic import SecretStr

    stored = lock(_settings(), SECRET)

    rotated = _settings(secret_key=SecretStr("another-secret-at-least-32-characters-long"))

    assert unlock(rotated, stored) is None
