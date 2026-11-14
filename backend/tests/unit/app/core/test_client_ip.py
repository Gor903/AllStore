"""Whose address an allowance is counted against.

Getting this wrong is not a small error. Believe the header from anybody and every limit is
bypassed by typing a different value into it; believe nobody while standing behind a proxy
and every visitor shares one bucket, so the first person to mistype a password spends
everyone else's attempts.
"""

from typing import Any

from starlette.requests import Request

from app.core.client_ip import UNKNOWN, allowance_key, client_ip
from app.core.config import Settings, get_settings

PROXY = "10.0.0.5"
PROXIES = ("10.0.0.0/24",)


def _settings(trusted: tuple[str, ...]) -> Settings:
    return get_settings().model_copy(update={"trusted_proxies": trusted})


def _request(peer: str | None, forwarded: str | None = None) -> Request:
    headers: list[tuple[bytes, bytes]] = []
    if forwarded is not None:
        headers.append((b"x-forwarded-for", forwarded.encode()))
    scope: dict[str, Any] = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/auth/login",
        "headers": headers,
        "client": None if peer is None else (peer, 51234),
    }
    return Request(scope)


def test_without_a_trusted_proxy_the_peer_is_the_client() -> None:
    """Nothing in front means the connection is the only thing worth believing."""
    request = _request("203.0.113.9", forwarded="1.2.3.4")

    assert client_ip(request, _settings(())) == "203.0.113.9"


def test_a_header_from_a_stranger_is_ignored() -> None:
    """The proxy is trusted, the caller is not, and this call came from the caller."""
    request = _request("198.51.100.7", forwarded="1.2.3.4")

    assert client_ip(request, _settings(PROXIES)) == "198.51.100.7"


def test_a_header_from_the_proxy_is_believed() -> None:
    request = _request(PROXY, forwarded="203.0.113.9")

    assert client_ip(request, _settings(PROXIES)) == "203.0.113.9"


def test_the_chain_is_read_from_our_end() -> None:
    """A caller who writes their own `X-Forwarded-For` ends up on the left of what the proxy
    appends. Reading the leftmost entry — which the header's shape invites — would take the
    value they typed; reading from the right stops at the first hop nobody vouched for."""
    request = _request(PROXY, forwarded="1.2.3.4, 203.0.113.9")

    assert client_ip(request, _settings(PROXIES)) == "203.0.113.9"


def test_several_of_our_own_hops_are_walked_through() -> None:
    request = _request(PROXY, forwarded="203.0.113.9, 10.0.0.8, 10.0.0.9")

    assert client_ip(request, _settings(PROXIES)) == "203.0.113.9"


def test_a_chain_that_is_all_ours_names_its_far_end() -> None:
    """Two ways this happens, same right answer.

    On the stand the visitor reaches nginx from the container network, so the single address
    nginx wrote is itself private. In a chain of our own proxies the last hop is the one
    nearest the caller. Naming the proxy that just handed us the request instead would name
    the one address we know for certain is not theirs — and put every visitor in one bucket.
    """
    request = _request(PROXY, forwarded="10.0.0.7, 10.0.0.8, 10.0.0.9")

    assert client_ip(request, _settings(PROXIES)) == "10.0.0.9"


def test_a_peer_that_is_not_an_address_vouches_for_nothing() -> None:
    """A transport that gives no address at all — an ASGI test client, a unix socket — is not
    a proxy, and a header arriving over one has to be ignored like any stranger's. Found by a
    surviving mutant: `_vouched_for` returning true for an unparseable address made every such
    caller trusted, and with it every value anybody typed into the header."""
    request = _request("testclient", forwarded="203.0.113.7")

    assert client_ip(request, _settings(PROXIES)) == "testclient"


def test_no_header_at_all_falls_back_to_the_peer() -> None:
    """Something inside the network calling us directly — a health check, usually."""
    assert client_ip(_request(PROXY), _settings(PROXIES)) == PROXY


def test_nonsense_in_the_header_is_not_treated_as_an_address() -> None:
    request = _request(PROXY, forwarded="not-an-address")

    assert client_ip(request, _settings(PROXIES)) == "not-an-address"


def test_a_connection_with_no_peer_shares_one_bucket() -> None:
    """An ASGI transport carrying no client, which in practice means a test."""
    assert client_ip(_request(None), _settings(PROXIES)) == UNKNOWN


def test_an_unparseable_entry_in_the_configuration_narrows_trust() -> None:
    """A stray comma must not widen what is believed, and must not stop the platform."""
    request = _request(PROXY, forwarded="203.0.113.9")

    assert client_ip(request, _settings(("", "nonsense", "10.0.0.0/24"))) == "203.0.113.9"
    assert client_ip(request, _settings(("nonsense",))) == PROXY


def test_one_ipv6_customer_spends_one_allowance() -> None:
    """A /64 is what a single subscriber is routinely handed. Counted per address, the next
    guess comes from the next address and the limit means nothing."""
    first = allowance_key("2001:db8:1:2::1")
    second = allowance_key("2001:db8:1:2:dead:beef:dead:beef")

    assert first == second == "2001:db8:1:2::/64"
    assert allowance_key("2001:db8:1:3::1") != first


def test_ipv4_is_counted_whole() -> None:
    """There one address really is what one caller has."""
    assert allowance_key("203.0.113.9") == "203.0.113.9"


def test_what_is_not_an_address_is_left_alone() -> None:
    """`UNKNOWN` is the one bucket every peerless connection shares, and it is not an address."""
    assert allowance_key(UNKNOWN) == UNKNOWN
    assert allowance_key("not-an-address") == "not-an-address"
