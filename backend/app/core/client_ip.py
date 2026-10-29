"""Who the request came from, when something stands in front of the application.

An allowance keyed on the wrong address is not an allowance. Behind nginx every visitor
arrives from the proxy's address, so a single bucket would hold the whole internet and the
first person to mistype their password would spend everybody else's attempts.

The header that carries the real address is also trivial to write by hand, so it is believed
only when the connection itself came from an address the deploy named. Nothing named means
nothing believed: the peer is the client, which is the right answer when the application is
reached directly.
"""

import ipaddress
from functools import lru_cache

from fastapi import Request

from app.core.config import Settings

Network = ipaddress.IPv4Network | ipaddress.IPv6Network

# What a connection with no address at all is counted as — an ASGI transport that carries no
# peer, which in practice means a test client. One shared bucket for them is correct.
UNKNOWN = "unknown"


@lru_cache
def _parsed(entries: tuple[str, ...]) -> tuple[Network, ...]:
    """Parsed once per distinct configuration rather than per request.

    An entry that is not an address or a network is dropped rather than raised on: the
    alternative is a platform that refuses to start because somebody left a comma in a
    variable, and the failure mode of dropping it is a narrower trust, not a wider one.
    """
    networks: list[Network] = []
    for entry in entries:
        try:
            networks.append(ipaddress.ip_network(entry, strict=False))
        except ValueError:
            continue
    return tuple(networks)


def _vouched_for(address: str, networks: tuple[Network, ...]) -> bool:
    try:
        host = ipaddress.ip_address(address)
    except ValueError:
        return False
    return any(host in network for network in networks)


def client_ip(request: Request, settings: Settings) -> str:
    """The furthest address along the chain that a trusted proxy vouched for.

    `X-Forwarded-For` is read from the right — the end our own proxy wrote, and the only end
    we have any reason to believe — and the walk stops at the first address nobody vouched
    for. That address is the client. Reading the leftmost entry instead, as the header's shape
    invites, would take whatever the caller typed into it.
    """
    peer = UNKNOWN if request.client is None else request.client.host
    networks = _parsed(tuple(settings.trusted_proxies))
    if not networks or not _vouched_for(peer, networks):
        return peer
    chain = [part.strip() for part in request.headers.get("x-forwarded-for", "").split(",")]
    for candidate in reversed([part for part in chain if part]):
        if not _vouched_for(candidate, networks):
            return candidate
    # every hop in the chain is ours, so the client is one of our own proxies
    return peer
