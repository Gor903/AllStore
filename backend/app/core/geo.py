"""Where an address is in the world, when anybody can tell us.

Nothing here resolves anything. It is the seam: a single function the session code asks, and
an answer of "we do not know" that the rest of the application is written to treat as
ordinary rather than as a failure. Plugging in a real source — a MaxMind database, a hosted
lookup — means replacing `_resolver` and nothing else.

**Why it is empty.** A source costs an account, a licence key and seventy megabytes in the
image, updated on a schedule. That is a decision with an owner, and it has not been made. The
plumbing is here anyway because the alternative is a column, a comparison and a letter all
arriving at once later, on top of code that was written without them in mind.

**Why "unknown" must never mean "suspicious".** Most of the world's addresses resolve to
nothing useful, and a visitor behind a corporate proxy or a privacy relay is not an intruder.
A rule that treats silence as a signal would ask half the platform to prove itself twice.
"""

from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class Place:
    """What a lookup can say about an address, and no more.

    Two fields because two are enough to notice the thing worth noticing: a session that was
    in one country this morning and another this afternoon. Finer than that — a city, a
    postcode — is a precision nobody acts on and a privacy cost nobody agreed to.
    """

    # ISO 3166-1 alpha-2, or whatever the source calls a country
    country: str | None = None
    # the autonomous system: which network operator, not which address
    asn: str | None = None

    @property
    def known(self) -> bool:
        return self.country is not None or self.asn is not None


Resolver = Callable[[str], Place]

# Replaced by `use`, never read directly — a module-level name read at call time is how a
# test ends up configuring the application it is testing by accident.
_resolver: Resolver | None = None


def use(resolver: Resolver | None) -> None:
    """Installs a source, or takes it away. Called at startup, and by tests."""
    global _resolver
    _resolver = resolver


def locate(ip: str | None) -> Place:
    """Where this address is, as far as anybody here can tell.

    Never raises and never blocks on anything: a lookup that cannot answer answers nothing.
    A sign-in must not fail because a geolocation database is being rebuilt.
    """
    if ip is None or _resolver is None:
        return Place()
    try:
        return _resolver(ip)
    except Exception:
        return Place()


def moved(before: Place, after: Place) -> bool:
    """Whether the difference between two places is worth acting on.

    Only when both are known. A session that had a country and now has none has not moved —
    the lookup has merely stopped answering, and treating that as travel would sign people
    out whenever the source had a bad day.

    The operator is compared as well as the country, because the interesting case is not
    really distance: it is the same session appearing on a network it has nothing to do with.
    """
    if not before.known or not after.known:
        return False
    if before.country is not None and after.country is not None:
        return before.country != after.country
    return before.asn != after.asn
