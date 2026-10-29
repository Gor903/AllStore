"""Which addresses count as ours.

A storefront's address is created the moment a seller picks a subdomain, so no list can name
them all. A pattern can — and a pattern that is slightly too generous is a permission granted
to whoever registers the right domain, which is why most of this file is about what it
refuses.
"""

import pytest

from app.core.config import Settings, get_settings


def _settings(**overrides: object) -> Settings:
    return get_settings().model_copy(update=overrides)


LOCAL = _settings(app_env="local", base_domain="allstore.localhost")
LIVE = _settings(app_env="production", base_domain="allstore.am")


@pytest.mark.parametrize(
    "origin",
    [
        "https://allstore.am",
        "https://cups.allstore.am",
        "https://a-shop-with-dashes.allstore.am",
    ],
)
def test_the_marketplace_and_its_storefronts_are_ours(origin: str) -> None:
    assert LIVE.is_our_origin(origin)


@pytest.mark.parametrize(
    ("origin", "why"),
    [
        ("https://allstore.am.evil.test", "a domain somebody registered to look like ours"),
        ("https://evil.test", "somebody else entirely"),
        ("http://allstore.am", "plain http, which production does not answer on"),
        ("https://allstore.am:8443", "a port nobody serves"),
        ("https://deep.nested.allstore.am", "two labels: a storefront has one"),
        ("https://ALLSTORE.am", "origins are compared as the browser sends them, lowercase"),
    ],
)
def test_and_nothing_else_is(origin: str, why: str) -> None:
    assert not LIVE.is_our_origin(origin), why


def test_the_local_stand_keeps_its_port() -> None:
    """Without it, every storefront request on the stand would be refused and the refusal
    would look like a bug in whatever page made it."""
    assert LOCAL.is_our_origin("http://allstore.localhost:8081")
    assert LOCAL.is_our_origin("http://cups.allstore.localhost:8081")
    assert LOCAL.is_our_origin("http://allstore.localhost")


def test_the_stand_does_not_vouch_for_the_live_domain() -> None:
    assert not LOCAL.is_our_origin("https://allstore.am")


def test_a_listed_origin_counts_however_it_looks() -> None:
    """The list is for addresses a deploy adds on purpose — a separate front end, a staging
    host — and they do not have to look like a storefront to be allowed."""
    configured = _settings(
        app_env="production",
        base_domain="allstore.am",
        cors_origins=["https://partner.example.com"],
    )

    assert configured.is_our_origin("https://partner.example.com")
