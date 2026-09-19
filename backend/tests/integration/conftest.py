from typing import Any

from httpx import AsyncClient, Response

from app.core.config import get_settings

BUYER_PAYLOAD = {"email": "Buyer@Example.com", "password": "buyer-password-1"}
SELLER_PAYLOAD = {
    "email": "seller@example.com",
    "password": "seller-password-1",
    "legal_name": 'ИП "Тестовый"',
    "display_name": "Тестовый магазин",
}


def csrf_headers(client: AsyncClient) -> dict[str, str]:
    settings = get_settings()
    return {settings.csrf_header_name: client.cookies[settings.csrf_cookie_name]}


async def register_buyer(client: AsyncClient, **overrides: Any) -> Response:
    return await client.post("/api/v1/auth/register/buyer", json={**BUYER_PAYLOAD, **overrides})


async def register_seller(client: AsyncClient, **overrides: Any) -> Response:
    return await client.post("/api/v1/auth/register/seller", json={**SELLER_PAYLOAD, **overrides})


async def login(client: AsyncClient, email: str, password: str) -> Response:
    return await client.post("/api/v1/auth/login", json={"email": email, "password": password})
