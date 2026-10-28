"""What passed between people, and who is allowed to know it did.

The leak this guards against is subtle: a feed is a side door. The listings stopped naming
staff to a moderator; a feed that carried "a moderator complained about this shop" would
name them again, by the back way.
"""

import uuid
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Business,
    BusinessCustomerBlock,
    BusinessStatus,
    Report,
    User,
    UserRole,
)
from tests.integration.conftest import act_as, seed_staff

pytestmark = pytest.mark.integration

INCIDENTS = "/api/v1/incidents"


async def a_person(session: AsyncSession, role: UserRole = UserRole.BUYER) -> User:
    user = User(email=f"{role}-{uuid.uuid4().hex}@example.com", password_hash="x", role=role)
    session.add(user)
    await session.flush()
    return user


async def a_shop_of(session: AsyncSession, owner: User) -> Business:
    shop = Business(
        owner_user_id=owner.id,
        legal_name="ИП Лавка",
        display_name="Лавка",
        status=BusinessStatus.ACTIVE,
    )
    session.add(shop)
    await session.flush()
    return shop


async def a_complaint(session: AsyncSession, reporter: User, shop: Business, reason: str) -> None:
    session.add(Report(reporter_user_id=reporter.id, business_id=shop.id, reason=reason))
    await session.flush()


async def test_a_complaint_shows_both_sides(api_client: AsyncClient, session: AsyncSession) -> None:
    buyer = await a_person(session)
    seller = await a_person(session, UserRole.SELLER)
    shop = await a_shop_of(session, seller)
    await a_complaint(session, buyer, shop, "Не отвечает неделю")
    await act_as(api_client, await seed_staff(session, UserRole.MODERATOR))

    body = (await api_client.get(INCIDENTS)).json()

    found = next(item for item in body["items"] if item["reason"] == "Не отвечает неделю")
    assert found["initiator_email"] == buyer.email
    assert found["counterpart_email"] == seller.email
    assert found["kind"] == "report"


async def test_a_shop_closing_its_door_is_an_incident_too(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    buyer = await a_person(session)
    seller = await a_person(session, UserRole.SELLER)
    shop = await a_shop_of(session, seller)
    session.add(
        BusinessCustomerBlock(
            business_id=shop.id,
            buyer_user_id=buyer.id,
            created_by_user_id=seller.id,
            reason="Грубость в переписке",
        )
    )
    await session.flush()
    await act_as(api_client, await seed_staff(session, UserRole.MODERATOR))

    body = (await api_client.get(f"{INCIDENTS}?kind=customer_block")).json()

    found = next(item for item in body["items"] if item["reason"] == "Грубость в переписке")
    assert found["initiator_email"] == seller.email
    assert found["counterpart_email"] == buyer.email


async def test_a_moderator_is_not_told_that_staff_exist(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    """The feed is the side door the listings were closed against."""
    hidden = await seed_staff(session, UserRole.MODERATOR)
    seller = await a_person(session, UserRole.SELLER)
    shop = await a_shop_of(session, seller)
    await a_complaint(session, hidden, shop, "Жалоба от модератора")
    await act_as(api_client, await seed_staff(session, UserRole.MODERATOR))

    body = (await api_client.get(INCIDENTS)).text

    assert hidden.email not in body
    assert "Жалоба от модератора" not in body


async def test_the_administrator_is_told(api_client: AsyncClient, session: AsyncSession) -> None:
    """Watching what the staff does is the whole point of the administrator's panel."""
    moderator = await seed_staff(session, UserRole.MODERATOR)
    seller = await a_person(session, UserRole.SELLER)
    shop = await a_shop_of(session, seller)
    await a_complaint(session, moderator, shop, "Жалоба от модератора")
    await act_as(api_client, await seed_staff(session, UserRole.ADMIN))

    body = (await api_client.get(INCIDENTS)).text

    assert moderator.email in body


async def test_the_feed_narrows_to_one_person(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    buyer = await a_person(session)
    other = await a_person(session)
    seller = await a_person(session, UserRole.SELLER)
    shop = await a_shop_of(session, seller)
    await a_complaint(session, buyer, shop, "Его жалоба")
    await a_complaint(session, other, shop, "Чужая жалоба")
    await act_as(api_client, await seed_staff(session, UserRole.MODERATOR))

    body = (await api_client.get(f"{INCIDENTS}?user_id={buyer.id}")).json()

    reasons = {item["reason"] for item in body["items"]}
    assert "Его жалоба" in reasons
    assert "Чужая жалоба" not in reasons


async def test_the_feed_narrows_to_a_period(api_client: AsyncClient, session: AsyncSession) -> None:
    buyer = await a_person(session)
    seller = await a_person(session, UserRole.SELLER)
    shop = await a_shop_of(session, seller)
    await a_complaint(session, buyer, shop, "Свежая жалоба")
    await act_as(api_client, await seed_staff(session, UserRole.MODERATOR))

    window = urlencode({"since": (datetime.now(UTC) + timedelta(days=1)).isoformat()})
    body = (await api_client.get(f"{INCIDENTS}?{window}")).json()

    assert body["items"] == []


async def test_newest_first(api_client: AsyncClient, session: AsyncSession) -> None:
    buyer = await a_person(session)
    seller = await a_person(session, UserRole.SELLER)
    shop = await a_shop_of(session, seller)
    await a_complaint(session, buyer, shop, "Первая")
    await a_complaint(session, buyer, shop, "Вторая")
    await act_as(api_client, await seed_staff(session, UserRole.MODERATOR))

    body = (await api_client.get(INCIDENTS)).json()

    stamps = [item["happened_at"] for item in body["items"]]
    assert stamps == sorted(stamps, reverse=True)


async def test_the_count_agrees_with_the_page(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    buyer = await a_person(session)
    seller = await a_person(session, UserRole.SELLER)
    shop = await a_shop_of(session, seller)
    for index in range(3):
        await a_complaint(session, buyer, shop, f"Жалоба {index}")
    await act_as(api_client, await seed_staff(session, UserRole.MODERATOR))

    body = (await api_client.get(f"{INCIDENTS}?user_id={buyer.id}&limit=2")).json()

    assert body["total"] == 3
    assert len(body["items"]) == 2


async def test_a_buyer_reaches_nothing(api_client: AsyncClient, session: AsyncSession) -> None:
    await act_as(api_client, await a_person(session), password="x")

    assert (await api_client.get(INCIDENTS)).status_code in (401, 403)
