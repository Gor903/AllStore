"""Nothing anywhere tells a moderator that other moderators or an administrator exist.

Written as a walk over every registered route rather than as a list of the ones that were
thought of. A list goes stale the first time somebody adds an endpoint, and the failure it
misses is silent — a screen that quietly starts naming staff. The walk gets the new route for
free and fails loudly.

What is checked is not the status code but the body: a route may legitimately refuse, redirect
or answer empty. What it may not do is contain a staff account's address or identifier.
"""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import create_app
from app.models import AccountBlock, AuditLog, UserRole
from tests.integration.conftest import act_as, seed_staff

pytestmark = pytest.mark.integration

# routes whose path takes something other than an account, or which answer with a side effect
SKIPPED_PREFIXES = ("/health", "/docs", "/openapi.json")


def readable_routes() -> list[str]:
    """Every GET the API publishes, with account identifiers left to be filled in.

    Read from the OpenAPI document rather than by walking `app.routes`: this FastAPI keeps
    included routers nested instead of flattening them, and a walk that assumed otherwise
    found nothing at all — which is how the guard below came to exist.
    """
    schema = create_app().openapi()
    return sorted(
        path
        for path, operations in schema["paths"].items()
        if "get" in operations and not path.startswith(SKIPPED_PREFIXES)
    )


async def test_the_walk_covers_a_realistic_number_of_routes() -> None:
    """A guard on the guard: a walk that silently stopped finding routes would pass forever."""
    assert len(readable_routes()) > 20


async def test_no_readable_route_names_staff_to_a_moderator(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    hidden_admin = await seed_staff(session, UserRole.ADMIN)
    hidden_moderator = await seed_staff(session, UserRole.MODERATOR)
    # give the hidden accounts something to show up in: a ban they laid and a journal entry
    session.add_all(
        [
            AccountBlock(
                user_id=hidden_moderator.id,
                actor_user_id=hidden_admin.id,
                reason="Чтобы было что найти",
            ),
            AuditLog(
                actor_user_id=hidden_admin.id,
                action="user.blocked",
                entity_type="user",
                entity_id=hidden_moderator.id,
            ),
        ]
    )
    await session.flush()

    looking = await seed_staff(session, UserRole.MODERATOR)
    await act_as(api_client, looking)

    secrets = {
        hidden_admin.email,
        str(hidden_admin.id),
        hidden_moderator.email,
        str(hidden_moderator.id),
    }
    leaked: list[tuple[str, str]] = []
    for path in readable_routes():
        # the identifiers that would reveal them, in the slot a caller would try
        address = path.format_map(
            {
                "user_id": hidden_moderator.id,
                "product_id": uuid.uuid4(),
                "business_id": uuid.uuid4(),
                "invitation_id": uuid.uuid4(),
                "category_id": uuid.uuid4(),
                "subdomain": "nothing",
                "conversation_id": uuid.uuid4(),
            }
        )
        body = (await api_client.get(address)).text
        leaked.extend((address, secret) for secret in secrets if secret in body)

    assert leaked == []


async def test_the_walk_would_notice_a_leak(api_client: AsyncClient, session: AsyncSession) -> None:
    """The same walk run by an administrator finds the staff, which is how we know it looks.

    Without this, a walk that fetched nothing at all would pass the test above and prove
    nothing whatsoever.
    """
    moderator = await seed_staff(session, UserRole.MODERATOR)
    admin = await seed_staff(session, UserRole.ADMIN)
    await act_as(api_client, admin)

    body = (await api_client.get("/api/v1/admin/users?limit=100")).text

    assert moderator.email in body
