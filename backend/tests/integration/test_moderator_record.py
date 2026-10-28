"""The administrator's window on the people who run the platform.

Every number here is counted from the decision itself rather than from a tally kept beside
it. A counter maintained in parallel can be wrong, and a wrong one on this screen would be
read as evidence of what somebody did.
"""

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from urllib.parse import urlencode

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    AccountBlock,
    AuditLog,
    Business,
    BusinessDecision,
    BusinessModerationReview,
    BusinessStatus,
    ModerationDecision,
    ModerationReview,
    Product,
    User,
    UserRole,
)
from tests.integration.conftest import act_as, seed_staff, seeded_category

pytestmark = pytest.mark.integration

JOURNAL = "/api/v1/admin/audit-logs"


async def a_shop(session: AsyncSession) -> Business:
    """A verdict is always about something, so the something has to exist."""
    owner = User(
        email=f"shopkeeper-{uuid.uuid4().hex}@example.com",
        password_hash="x",
        role=UserRole.SELLER,
    )
    session.add(owner)
    await session.flush()
    shop = Business(
        owner_user_id=owner.id,
        legal_name="ИП Подопытный",
        display_name="Подопытный",
        status=BusinessStatus.ACTIVE,
    )
    session.add(shop)
    await session.flush()
    return shop


async def a_product(session: AsyncSession) -> Product:
    shop = await a_shop(session)
    category = await seeded_category(session)
    product = Product(
        business_id=shop.id,
        category_id=category.id,
        name="Кружка",
        price=Decimal("1500.00"),
        currency="AMD",
        stock_quantity=1,
    )
    session.add(product)
    await session.flush()
    return product


async def test_the_record_counts_what_the_moderator_decided(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    moderator = await seed_staff(session, UserRole.MODERATOR)
    admin = await seed_staff(session, UserRole.ADMIN)
    other = await seed_staff(session, UserRole.MODERATOR)
    product = await a_product(session)
    session.add_all(
        [
            ModerationReview(
                product_id=product.id,
                moderator_id=moderator.id,
                decision=ModerationDecision.APPROVED,
            ),
            ModerationReview(
                product_id=product.id,
                moderator_id=moderator.id,
                decision=ModerationDecision.APPROVED,
            ),
            ModerationReview(
                product_id=product.id,
                moderator_id=moderator.id,
                decision=ModerationDecision.REJECTED,
                reason="Нет фото",
            ),
            # another moderator's work must not land on this one's record
            ModerationReview(
                product_id=product.id,
                moderator_id=other.id,
                decision=ModerationDecision.APPROVED,
            ),
        ]
    )
    await session.flush()
    await act_as(api_client, admin)

    body = (await api_client.get(f"/api/v1/admin/moderators/{moderator.id}")).json()

    assert body["products_approved"] == 2
    assert body["products_rejected"] == 1
    assert body["moderator"]["email"] == moderator.email


async def test_a_lifted_ban_still_counts_as_something_they_did(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    moderator = await seed_staff(session, UserRole.MODERATOR)
    admin = await seed_staff(session, UserRole.ADMIN)
    barred = await seed_staff(session, UserRole.MODERATOR)
    session.add(
        AccountBlock(
            user_id=barred.id,
            actor_user_id=moderator.id,
            reason="Старое",
            revoked_at=datetime.now(UTC),
        )
    )
    await session.flush()
    await act_as(api_client, admin)

    body = (await api_client.get(f"/api/v1/admin/moderators/{moderator.id}")).json()

    # the question is what this moderator did, not what is still in force
    assert body["accounts_blocked"] == 1


async def test_an_account_that_is_not_a_moderator_has_no_record(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    admin = await seed_staff(session, UserRole.ADMIN)
    await act_as(api_client, admin)

    response = await api_client.get(f"/api/v1/admin/moderators/{admin.id}")

    assert response.status_code == 404


async def test_business_verdicts_are_counted_apart_from_product_ones(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    moderator = await seed_staff(session, UserRole.MODERATOR)
    admin = await seed_staff(session, UserRole.ADMIN)
    shop = await a_shop(session)
    session.add_all(
        [
            BusinessModerationReview(
                business_id=shop.id,
                moderator_id=moderator.id,
                decision=BusinessDecision.APPROVED,
            ),
            BusinessModerationReview(
                business_id=shop.id,
                moderator_id=moderator.id,
                decision=BusinessDecision.REJECTED,
                reason="Нет ИНН",
            ),
        ]
    )
    await session.flush()
    await act_as(api_client, admin)

    body = (await api_client.get(f"/api/v1/admin/moderators/{moderator.id}")).json()

    assert body["businesses_approved"] == 1
    assert body["businesses_refused"] == 1
    assert body["products_approved"] == 0


async def test_the_journal_narrows_to_one_actor(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    moderator = await seed_staff(session, UserRole.MODERATOR)
    admin = await seed_staff(session, UserRole.ADMIN)
    session.add_all(
        [
            AuditLog(actor_user_id=moderator.id, action="product.approved", entity_type="product"),
            AuditLog(actor_user_id=admin.id, action="category.created", entity_type="category"),
        ]
    )
    await session.flush()
    await act_as(api_client, admin)

    body = (await api_client.get(f"{JOURNAL}?actor_id={moderator.id}")).json()

    assert {entry["action"] for entry in body["items"]} == {"product.approved"}
    assert body["total"] == 1


async def test_the_journal_matches_an_action_by_its_prefix(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    """So `user.` asks for every decision about accounts without naming each of them."""
    admin = await seed_staff(session, UserRole.ADMIN)
    session.add_all(
        [
            AuditLog(actor_user_id=admin.id, action="user.blocked", entity_type="user"),
            AuditLog(actor_user_id=admin.id, action="user.role_changed", entity_type="user"),
            AuditLog(actor_user_id=admin.id, action="product.approved", entity_type="product"),
        ]
    )
    await session.flush()
    await act_as(api_client, admin)

    body = (await api_client.get(f"{JOURNAL}?action=user.")).json()

    assert {entry["action"] for entry in body["items"]} == {"user.blocked", "user.role_changed"}


async def test_the_journal_narrows_to_a_period(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    admin = await seed_staff(session, UserRole.ADMIN)
    old = AuditLog(actor_user_id=admin.id, action="product.approved", entity_type="product")
    session.add(old)
    await session.flush()
    old.created_at = datetime.now(UTC) - timedelta(days=30)
    recent = AuditLog(actor_user_id=admin.id, action="product.rejected", entity_type="product")
    session.add(recent)
    await session.flush()

    await act_as(api_client, admin)
    since = urlencode({"since": (datetime.now(UTC) - timedelta(days=1)).isoformat()})
    body = (await api_client.get(f"{JOURNAL}?{since}")).json()

    actions = {entry["action"] for entry in body["items"]}
    assert "product.rejected" in actions
    assert "product.approved" not in actions


async def test_the_journal_count_agrees_with_the_filter(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    admin = await seed_staff(session, UserRole.ADMIN)
    session.add_all(
        [
            AuditLog(actor_user_id=admin.id, action="user.blocked", entity_type="user"),
            AuditLog(actor_user_id=admin.id, action="product.approved", entity_type="product"),
        ]
    )
    await session.flush()
    await act_as(api_client, admin)

    body = (await api_client.get(f"{JOURNAL}?action=user.")).json()

    assert body["total"] == len(body["items"])


async def test_a_moderator_reads_no_record_and_no_journal(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    moderator = await seed_staff(session, UserRole.MODERATOR)
    await act_as(api_client, moderator)

    assert (await api_client.get(JOURNAL)).status_code == 403
    assert (await api_client.get(f"/api/v1/admin/moderators/{moderator.id}")).status_code == 403
