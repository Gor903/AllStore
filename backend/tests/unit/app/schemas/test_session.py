"""The list of devices an account is signed in on.

The token is not in this shape and never will be — not even a prefix of it. A list of devices
is the screen people are told to check when something feels wrong, which makes it a screen an
attacker reads too; the only reason to put a fragment of a live credential on it would be to
help somebody recognise their own laptop, and the time and the browser do that.

The identifier is the family rather than the row, because renewing a token must not look like
a new device: a person checking this screen would see one stranger per hour of their own use.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from app.models import Session
from app.schemas.session import DeviceKeyRequest, SessionRead


def _row(**overrides: object) -> Session:
    now = datetime.now(UTC)
    fields: dict[str, object] = {
        "id": uuid.uuid4(),
        "family_id": uuid.uuid4(),
        "user_id": uuid.uuid4(),
        "user_agent": "Firefox на Linux",
        "ip": "203.0.113.7",
        "created_at": now - timedelta(days=3),
        "last_seen_at": now,
    }
    return Session(**{**fields, **overrides})


def test_a_device_is_named_by_its_family_and_not_by_the_token_in_hand() -> None:
    """Renewing a token writes a new row in the same family. Showing the row would mean the
    owner sees a new device every time their browser renews, which is every few minutes."""
    row = _row()

    read = SessionRead.of(row, current=False)

    assert read.id == row.family_id
    assert read.id != row.id


def test_nothing_about_the_token_itself_is_listed() -> None:
    """The way to be sure no fragment of a live credential reaches this screen is for the
    shape to have nowhere to put one."""
    fields = set(SessionRead.model_fields)

    assert fields == {"id", "user_agent", "ip", "created_at", "last_seen_at", "current"}
    assert not any("token" in field or "hash" in field for field in fields)


def test_the_screen_can_say_which_one_is_this_one() -> None:
    """Otherwise somebody ending "all other sessions" has to guess which line is their own."""
    row = _row()

    assert SessionRead.of(row, current=True).current is True
    assert SessionRead.of(row, current=False).current is False


def test_a_device_is_named_by_what_its_browser_said_it_was() -> None:
    """Found by a surviving mutant: every assertion here was about the empty case, so a
    `SessionRead` that dropped the user agent entirely passed — and the screen people are told
    to check when something feels wrong would have shown them a list of blank lines."""
    row = _row(user_agent="Firefox на Linux", ip="203.0.113.7")

    read = SessionRead.of(row, current=False)

    assert read.user_agent == "Firefox на Linux"
    assert read.ip == "203.0.113.7"


def test_a_device_nobody_can_name_is_still_a_device() -> None:
    """A browser that sends no user agent and a request with no address recorded are both
    ordinary; refusing to list them would hide a session from its owner."""
    read = SessionRead.of(_row(user_agent=None, ip=None), current=False)

    assert read.user_agent is None
    assert read.ip is None


def test_both_times_are_carried_because_one_of_them_is_the_question() -> None:
    """ "Signed in three days ago and last seen a minute ago" is what tells somebody whether
    the line is theirs; either half alone does not."""
    row = _row()

    read = SessionRead.of(row, current=False)

    assert read.created_at == row.created_at
    assert read.last_seen_at == row.last_seen_at


@pytest.mark.parametrize("key", ["a", "k" * 2048])
def test_a_public_key_of_a_plausible_size_is_taken(key: str) -> None:
    assert DeviceKeyRequest(public_key=key).public_key == key


@pytest.mark.parametrize("key", ["", "k" * 2049])
def test_a_public_key_that_is_nothing_or_far_too_much_is_refused(key: str) -> None:
    """An SPKI key for P-256 is a hundred-odd bytes of base64; the ceiling is there so that
    nobody can post a megabyte into the column by calling it a key."""
    with pytest.raises(ValidationError):
        DeviceKeyRequest(public_key=key)
