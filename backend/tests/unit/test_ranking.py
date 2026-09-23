import uuid

from app.services.ranking import merge


def identifiers(count: int) -> list[uuid.UUID]:
    return [uuid.UUID(int=number) for number in range(1, count + 1)]


def test_one_ranking_keeps_its_order() -> None:
    ids = identifiers(3)

    assert merge(ids) == ids


def test_what_both_sides_found_comes_first() -> None:
    """Two independent votes outweigh a first place in one list alone."""
    a, b, c = identifiers(3)

    assert merge([a, b], [c, b])[0] == b


def test_nothing_is_lost_and_nothing_doubles() -> None:
    a, b, c = identifiers(3)

    merged = merge([a, b], [b, c])

    assert sorted(merged, key=str) == sorted([a, b, c], key=str)


def test_an_empty_side_changes_nothing() -> None:
    ids = identifiers(3)

    assert merge(ids, []) == ids
    assert merge([], ids) == ids


def test_the_order_is_the_same_every_time() -> None:
    """Otherwise page two could repeat a product from page one."""
    a, b, c, d = identifiers(4)

    assert merge([a, b, c], [d, c]) == merge([a, b, c], [d, c])


def test_a_tie_goes_to_the_more_trusted_list() -> None:
    """First place in both lists is a draw on score — and the words beat the guess."""
    a, b = identifiers(2)

    assert merge([a], [b]) == [a, b]
