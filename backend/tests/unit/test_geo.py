"""The seam where a geolocation source would plug in, and what it promises while empty.

Two of these are about the empty case, and they are the important ones: the whole arrangement
is written so that "nobody knows where this is" is ordinary rather than alarming, and a rule
that treated silence as a signal would ask half the platform to prove itself twice.
"""

from collections.abc import Iterator

import pytest

from app.core import geo
from app.core.geo import Place


@pytest.fixture(autouse=True)
def no_source() -> Iterator[None]:
    """The resolver is one per process, so a test that installs one puts it back."""
    yield
    geo.use(None)


def test_with_no_source_nothing_is_known() -> None:
    assert geo.locate("203.0.113.7") == Place()
    assert not geo.locate("203.0.113.7").known


def test_with_a_source_it_answers() -> None:
    geo.use(lambda ip: Place(country="AM", asn="AS1234"))

    assert geo.locate("203.0.113.7") == Place(country="AM", asn="AS1234")


def test_a_source_that_falls_over_is_absorbed() -> None:
    """A sign-in must not fail because a geolocation database is being rebuilt."""

    def broken(ip: str) -> Place:
        raise RuntimeError("the database is being rebuilt")

    geo.use(broken)

    assert geo.locate("203.0.113.7") == Place()


def test_an_address_nobody_gave_is_nowhere() -> None:
    geo.use(lambda ip: Place(country="AM"))

    assert geo.locate(None) == Place()


def test_a_change_of_country_is_a_move() -> None:
    assert geo.moved(Place(country="AM"), Place(country="DE"))


def test_a_change_of_operator_is_a_move_when_that_is_all_there_is() -> None:
    """The interesting case is not really distance: it is the same session turning up on a
    network it has nothing to do with."""
    assert geo.moved(Place(asn="AS1234"), Place(asn="AS5678"))


def test_the_same_place_is_not() -> None:
    assert not geo.moved(Place(country="AM", asn="AS1"), Place(country="AM", asn="AS2"))


def test_losing_the_answer_is_not_a_move() -> None:
    """A lookup that stopped answering has not moved anybody. Treating it as travel would
    sign people out whenever the source had a bad day."""
    assert not geo.moved(Place(country="AM"), Place())
    assert not geo.moved(Place(), Place(country="DE"))
    assert not geo.moved(Place(), Place())
