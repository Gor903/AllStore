"""Which storefront a public request is addressed to, read from the Host header.

Only public storefront data hangs off this. Nothing a seller owns is ever resolved by Host —
the dashboard reads the session — so a forged header cannot reach private data. What it can do
is name a shop, and that is what is tested: the host is read the way DNS reads it, the names
the platform keeps for itself are not shops, and anything else is a 404 rather than a 500.
"""

from typing import Any
from uuid import uuid4

import pytest
from fastapi import FastAPI, status
from fastapi.testclient import TestClient

from app.core.config import Settings, get_settings
from app.core.errors import NotFoundError, register_exception_handlers
from app.db.session import get_session
from app.deps.settings import settings_dep
from app.deps.tenant import CurrentStore, get_current_store
from app.models import Store, StoreStatus
from app.services import stores as stores_service


def _settings(**overrides: object) -> Settings:
    return get_settings().model_copy(
        update={
            "base_domain": "allstore.am",
            "reserved_subdomains": ["www", "api", "admin"],
            **overrides,
        }
    )


def _client(monkeypatch: pytest.MonkeyPatch, settings: Settings) -> tuple[TestClient, list[str]]:
    """A public route behind the dependency, with the lookup itself stubbed out: what is under
    test is which name is asked for, not what the database answers."""
    asked: list[str] = []

    async def _lookup(session: object, subdomain: str) -> Store:
        asked.append(subdomain)
        return Store(
            id=uuid4(),
            business_id=uuid4(),
            subdomain=subdomain,
            theme_id="default",
            status=StoreStatus.ACTIVE,
        )

    monkeypatch.setattr(stores_service, "get_public_store", _lookup)

    app = FastAPI()
    register_exception_handlers(app)
    app.dependency_overrides[settings_dep] = lambda: settings
    app.dependency_overrides[get_session] = lambda: None

    @app.get("/storefront")
    async def storefront(store: CurrentStore) -> dict[str, str]:
        return {"subdomain": store.subdomain}

    return TestClient(app), asked


def test_the_shop_is_named_by_the_host_the_visitor_arrived_on(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, asked = _client(monkeypatch, _settings())

    response = client.get("/storefront", headers={"host": "cups.allstore.am"})

    assert response.status_code == status.HTTP_200_OK
    assert asked == ["cups"]


def test_the_host_is_read_the_way_dns_reads_it(monkeypatch: pytest.MonkeyPatch) -> None:
    """Case does not distinguish hosts, and a port is not part of the name."""
    client, asked = _client(monkeypatch, _settings())

    client.get("/storefront", headers={"host": "CUPS.allstore.am:8080"})

    assert asked == ["cups"]


@pytest.mark.parametrize("reserved", ["www", "api", "admin"])
def test_a_name_the_platform_keeps_for_itself_is_not_a_shop(
    monkeypatch: pytest.MonkeyPatch, reserved: str
) -> None:
    """Otherwise registering `api` as a storefront would mean answering for the API's own
    host, which is a way to be handed other people's requests."""
    client, asked = _client(monkeypatch, _settings())

    response = client.get("/storefront", headers={"host": f"{reserved}.allstore.am"})

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.json()["error"]["code"] == "not_found"
    assert asked == [], "a reserved name is refused before anything is looked up"


@pytest.mark.parametrize(
    "host",
    [
        "allstore.am",  # the marketplace itself is not a storefront
        "example.com",  # somebody else's domain entirely
        "cups.example.com",  # a shop name under a domain that is not ours
        "deep.cups.allstore.am",  # two levels down is not a storefront either
    ],
)
def test_a_host_that_names_no_shop_is_a_404(monkeypatch: pytest.MonkeyPatch, host: str) -> None:
    client, asked = _client(monkeypatch, _settings())

    response = client.get("/storefront", headers={"host": host})

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert asked == []


async def test_a_request_with_no_host_at_all_is_a_404_rather_than_a_crash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An HTTP/1.0 client sends none, and a scanner sends whatever it likes."""
    _, asked = _client(monkeypatch, _settings())
    # asked directly: the test client always sends a host of its own
    request: Any = type("Request", (), {"headers": {}})()

    with pytest.raises(NotFoundError, match="Магазин не найден"):
        await get_current_store(request, _settings(), None)  # type: ignore[arg-type]

    assert asked == []
