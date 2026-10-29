"""Whose address an allowance is counted against.

Getting this wrong is not a small error. Believe the header from anybody and every limit is
bypassed by typing a different value into it; believe nobody while standing behind a proxy
and every visitor shares one bucket, so the first person to mistype a password spends
everyone else's attempts.
"""

from typing import Any

from starlette.requests import Request

from app.core.client_ip import UNKNOWN, client_ip
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


def test_a_chain_that_is_all_ours_falls_back_to_the_peer() -> None:
    """A health check from inside: there is no outside client to name."""
    request = _request(PROXY, forwarded="10.0.0.8, 10.0.0.9")

    assert client_ip(request, _settings(PROXIES)) == PROXY


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
