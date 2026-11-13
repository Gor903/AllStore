import pytest

from app.core.hosts import subdomain_from_host

BASE = "allstore.am"


@pytest.mark.parametrize(
    ("host", "expected"),
    [
        ("cups.allstore.am", "cups"),
        ("CUPS.AllStore.AM", "cups"),  # DNS is case-insensitive
        ("cups.allstore.am:8080", "cups"),  # a port is not part of the name
        (" cups.allstore.am ", "cups"),
        ("my-shop.allstore.am", "my-shop"),
    ],
)
def test_storefront_hosts_resolve(host: str, expected: str) -> None:
    assert subdomain_from_host(host, BASE) == expected


@pytest.mark.parametrize(
    "host",
    [
        None,  # no Host header at all
        "",
        "allstore.am",  # the marketplace itself is not a storefront
        "evil.com",
        "cups.evil.com",
        "notallstore.am",  # ends with the domain as text, but is not under it
        "evilallstore.am",
        "a.b.allstore.am",  # a deeper level is not routed
        ".allstore.am",  # empty label
        "cups-.allstore.am",  # not a valid label
        "-cups.allstore.am",
        "my_shop.allstore.am",
        "ab.allstore.am",  # shorter than the minimum
        "[::1]",  # an address is never a storefront
        "[::1]:8080",
    ],
)
def test_hosts_that_are_not_storefronts(host: str | None) -> None:
    assert subdomain_from_host(host, BASE) is None


def test_the_base_domain_is_compared_case_insensitively() -> None:
    assert subdomain_from_host("cups.ALLSTORE.am", "AllStore.AM") == "cups"
