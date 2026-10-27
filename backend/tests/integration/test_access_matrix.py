"""Раздел 6 of the refactor plan, asserted route by route against the real API.

Every other suite checks one feature deeply. This one checks one thing shallowly across the
whole surface: for each route that matters, which roles the backend lets in and which it
turns away. It is the test that fails when somebody adds an endpoint and forgets the gate.

What counts as "allowed" here is deliberately narrow: not 401 and not 403. A probe may well
answer 404 or 409 — the identifiers are invented and nothing is set up — and that is the
right answer, because it means authorization let the caller through and the request failed
on its own merits. Testing the outcomes too would make this a slow copy of five other files;
testing the gate is what the matrix is actually about.
"""

import uuid
from dataclasses import dataclass, field
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import UserRole
from tests.integration.conftest import (
    act_as,
    anonymous,
    csrf_headers,
    register_buyer,
    register_seller,
    seed_staff,
)

pytestmark = pytest.mark.integration

GUEST = "guest"
ROLES = [GUEST, "buyer", "seller", "moderator", "admin"]

# a placeholder, so a probe that gets past the gate fails on "no such thing" rather than on
# having touched somebody's real data
ANY_ID = uuid.uuid4()

DENIED = {401, 403}


@dataclass(frozen=True)
class Probe:
    """One cell of the matrix: a request, and who the platform lets make it."""

    name: str
    method: str
    path: str
    allowed: frozenset[str]
    body: dict[str, Any] | None = field(default=None)


def probe(
    name: str, method: str, path: str, *allowed: str, body: dict[str, Any] | None = None
) -> Probe:
    """The body is a dict rather than keyword arguments: a probe needs to send fields called
    `name` and `role`, and those are this function's own parameter names."""
    return Probe(name, method, path, frozenset(allowed), body)


STAFF = ("moderator", "admin")
EVERYONE = tuple(ROLES)
REASON = "Нарушение правил площадки"

MATRIX = [
    # Просмотр публичного каталога
    probe("каталог товаров", "GET", "/api/v1/catalog/products", *EVERYONE),
    probe("список магазинов", "GET", "/api/v1/catalog/stores", *EVERYONE),
    probe("категории", "GET", "/api/v1/catalog/categories", *EVERYONE),
    # Жалобы: гость тоже должен иметь возможность пожаловаться
    probe(
        "подать жалобу",
        "POST",
        "/api/v1/reports",
        *EVERYONE,
        body={"product_id": str(ANY_ID), "reason": REASON},
    ),
    # Создание и управление своим магазином
    probe("свой бизнес", "GET", "/api/v1/users/me/business", "seller"),
    probe("создать витрину", "POST", "/api/v1/stores", "seller", body={"subdomain": "probe-shop"}),
    probe(
        "настройки витрины", "PATCH", "/api/v1/stores/me", "seller", body={"description": "Опись"}
    ),
    probe("повторная подача заявки", "POST", "/api/v1/users/me/business/resubmit", "seller"),
    # Свои товары
    probe("список своих товаров", "GET", "/api/v1/products", "seller"),
    probe(
        "создать товар",
        "POST",
        "/api/v1/products",
        "seller",
        body={"category_id": str(ANY_ID), "name": "Товар", "price": "100.00"},
    ),
    # Своя дверь: закрыть магазин покупателю
    probe("закрытые покупатели", "GET", "/api/v1/stores/me/blocked-buyers", "seller"),
    probe(
        "закрыть магазин покупателю",
        "POST",
        "/api/v1/stores/me/blocked-buyers",
        "seller",
        body={"email": "buyer@example.com", "reason": REASON},
    ),
    # Одобрение продавцов и товаров
    probe("очередь товаров", "GET", "/api/v1/moderation/products", *STAFF),
    probe("очередь продавцов", "GET", "/api/v1/moderation/businesses", *STAFF),
    probe("очередь жалоб", "GET", "/api/v1/moderation/reports", *STAFF),
    probe("поиск по каталогу для модерации", "GET", "/api/v1/moderation/catalog?q=чай", *STAFF),
    probe("одобрить товар", "POST", f"/api/v1/moderation/products/{ANY_ID}/approve", *STAFF),
    probe(
        "отклонить заявку продавца",
        "POST",
        f"/api/v1/moderation/businesses/{ANY_ID}/reject",
        *STAFF,
        body={"reason": REASON},
    ),
    # Глобальные баны
    probe("список подопечных аккаунтов", "GET", "/api/v1/accounts", *STAFF),
    probe(
        "заблокировать аккаунт",
        "POST",
        f"/api/v1/accounts/{ANY_ID}/block",
        *STAFF,
        body={"reason": REASON},
    ),
    probe("разблокировать аккаунт", "POST", f"/api/v1/accounts/{ANY_ID}/unblock", *STAFF),
    probe("история блокировок", "GET", f"/api/v1/accounts/{ANY_ID}/blocks", *STAFF),
    probe("чужие локальные блокировки", "GET", f"/api/v1/accounts/{ANY_ID}/store-blocks", *STAFF),
    # Администрирование: роли, приглашения, настройки, журнал
    probe("список всех аккаунтов", "GET", "/api/v1/admin/users", "admin"),
    probe(
        "сменить роль",
        "POST",
        f"/api/v1/admin/users/{ANY_ID}/role",
        "admin",
        body={"role": "moderator"},
    ),
    probe(
        "передать администрирование",
        "POST",
        f"/api/v1/admin/users/{ANY_ID}/transfer-admin",
        "admin",
    ),
    probe("приглашения модераторов", "GET", "/api/v1/admin/moderator-invitations", "admin"),
    probe(
        "выдать приглашение",
        "POST",
        "/api/v1/admin/moderator-invitations",
        "admin",
        body={"email": "invited@example.com"},
    ),
    probe(
        "отозвать приглашение",
        "POST",
        f"/api/v1/admin/moderator-invitations/{ANY_ID}/revoke",
        "admin",
    ),
    probe("журнал аудита", "GET", "/api/v1/admin/audit-logs", "admin"),
    probe("категории в админке", "GET", "/api/v1/admin/categories", "admin"),
    probe(
        "завести категорию",
        "POST",
        "/api/v1/admin/categories",
        "admin",
        body={"name": "Категория", "slug": "probe-category"},
    ),
    probe(
        "снять локальную блокировку поверх продавца",
        "POST",
        f"/api/v1/store-blocks/{ANY_ID}/revoke",
        "admin",
    ),
]


async def become(client: AsyncClient, session: AsyncSession, role: str) -> None:
    """Puts the client in the given role, by the only route that role actually has."""
    await anonymous(client)
    if role == GUEST:
        return
    if role == "buyer":
        await register_buyer(client, email=f"buyer-{uuid.uuid4().hex}@example.com")
        return
    if role == "seller":
        await register_seller(client, email=f"seller-{uuid.uuid4().hex}@example.com")
        return
    await act_as(client, await seed_staff(session, UserRole(role)))


async def send(client: AsyncClient, item: Probe) -> int:
    headers = {} if client.cookies.get("allstore_csrf") is None else csrf_headers(client)
    response = await client.request(item.method, item.path, json=item.body, headers=headers)
    return response.status_code


@pytest.mark.parametrize("role", ROLES)
@pytest.mark.parametrize("item", MATRIX, ids=lambda item: item.name)
async def test_the_access_matrix_holds(
    api_client: AsyncClient, session: AsyncSession, item: Probe, role: str
) -> None:
    await become(api_client, session, role)

    status = await send(api_client, item)

    if role in item.allowed:
        assert status not in DENIED, f"{role} должен иметь доступ: {item.name} → {status}"
    else:
        assert status in DENIED, f"{role} не должен иметь доступа: {item.name} → {status}"


@pytest.mark.parametrize("role", [r for r in ROLES if r != GUEST])
async def test_an_anonymous_caller_is_unauthenticated_rather_than_forbidden(
    api_client: AsyncClient, session: AsyncSession, role: str
) -> None:
    """401 and 403 are different answers: one says who are you, the other says not you.

    Collapsing them would tell a signed-out visitor to go away instead of to sign in.
    """
    await anonymous(api_client)

    assert (await api_client.get("/api/v1/admin/users")).status_code == 401
    assert (await api_client.get("/api/v1/accounts")).status_code == 401
    assert (await api_client.get("/api/v1/products")).status_code == 401


async def test_a_mutation_without_the_csrf_header_is_refused_for_every_role(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    """The gate the matrix does not describe and every browser mutation passes through."""
    for role in ("seller", "moderator", "admin"):
        await become(api_client, session, role)
        response = await api_client.post(
            f"/api/v1/accounts/{ANY_ID}/block", json={"reason": REASON}
        )
        assert response.status_code == 403, role
