from httpx import AsyncClient


async def test_health_returns_ok(client: AsyncClient) -> None:
    response = await client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


async def test_unknown_route_uses_error_envelope(client: AsyncClient) -> None:
    response = await client.get("/no-such-route")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"
