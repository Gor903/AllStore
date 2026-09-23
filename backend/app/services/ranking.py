"""Merging two orderings into one.

Reciprocal rank fusion: each list votes for a product with a weight that falls off with its
position, and the votes are added. It needs no calibration between the two sides, which is the
point — a trigram similarity and a cosine distance are not numbers that can be compared, but
"third in one list, first in the other" is something that can.
"""

import uuid
from collections.abc import Sequence

# the constant from the original formula: it flattens the difference between the top positions
# so that a single list cannot decide the whole ranking on its own
RRF_K = 60


def merge(*rankings: Sequence[uuid.UUID]) -> list[uuid.UUID]:
    """One ordering out of several, best first, without duplicates.

    Pass the rankings in order of authority: a tie is broken in favour of the earlier list.
    A product that literally contains the words the visitor typed and one the search merely
    considers close will otherwise trade places at random, and the first of those is the one
    the visitor asked for.
    """
    scores: dict[uuid.UUID, float] = {}
    found_in: dict[uuid.UUID, tuple[int, int]] = {}
    for index, ranking in enumerate(rankings):
        for position, identifier in enumerate(ranking):
            scores[identifier] = scores.get(identifier, 0.0) + 1.0 / (RRF_K + position + 1)
            found_in.setdefault(identifier, (index, position))
    # the identifier itself is the last resort, so the order never depends on dictionary luck
    return sorted(scores, key=lambda item: (-scores[item], found_in[item], str(item)))
