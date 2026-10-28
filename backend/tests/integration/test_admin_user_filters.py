"""Narrowing the administrator's list of accounts.

An absent filter asks nothing. `has_bans=false` asks for the accounts that have never been
barred — a different question from not asking, and the one most easily got wrong.
"""

from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models import AccountBlock, Business, BusinessStatus, Report, User, UserRole, UserStatus
from tests.integration.conftest import act_as, seed_staff

pytestmark = pytest.mark.integration

USERS_URL = "/api/v1/admin/users"
PASSWORD = "filters-password-1"


async def an_account(
    session: AsyncSession,
    email: str,
    *,
    role: UserRole = UserRole.BUYER,
    status: UserStatus = UserStatus.ACTIVE,
    phone: str | None = None,
    last_login_at: datetime | None = None,
) -> User:
    user = User(
        email=email,
        password_hash=hash_password(PASSWORD),
        role=role,
        status=status,
        phone=phone,
        last_login_at=last_login_at,
    )
    session.add(user)
    await session.flush()
    return user


async def emails_from(client: AsyncClient, query: str) -> set[str]:
    response = await client.get(f"{USERS_URL}?{query}&limit=100")
    assert response.status_code == 200, response.text
    return {item["email"] for item in response.json()["items"]}


async def test_the_search_matches_the_phone_as_well_as_the_address(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    """The login is an address or a phone, and whoever is searching knows which they have."""
    await act_as(api_client, await seed_staff(session, UserRole.ADMIN))
    await an_account(session, "by-phone@example.com", phone="+37410999001")
    await an_account(session, "by-address@example.com", phone="+37410888002")

    assert await emails_from(api_client, "q=999001") == {"by-phone@example.com"}
    assert await emails_from(api_client, "q=by-address") == {"by-address@example.com"}


async def test_the_role_filter_takes_more_than_one(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    await act_as(api_client, await seed_staff(session, UserRole.ADMIN))
    await an_account(session, "a-buyer@example.com", role=UserRole.BUYER)
    await an_account(session, "a-seller@example.com", role=UserRole.SELLER)
    await an_account(session, "a-moderator@example.com", role=UserRole.MODERATOR)

    found = await emails_from(api_client, "role=buyer&role=seller")

    assert "a-buyer@example.com" in found
    assert "a-seller@example.com" in found
    assert "a-moderator@example.com" not in found


async def test_the_status_filter_narrows_to_the_barred(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    await act_as(api_client, await seed_staff(session, UserRole.ADMIN))
    await an_account(session, "active@example.com")
    await an_account(session, "barred@example.com", status=UserStatus.BLOCKED)

    found = await emails_from(api_client, "status=blocked")

    assert "barred@example.com" in found
    assert "active@example.com" not in found


async def test_the_last_login_window_excludes_those_who_never_came_back(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    await act_as(api_client, await seed_staff(session, UserRole.ADMIN))
    now = datetime.now(UTC)
    await an_account(session, "recent@example.com", last_login_at=now - timedelta(days=1))
    await an_account(session, "stale@example.com", last_login_at=now - timedelta(days=90))
    await an_account(session, "never@example.com")

    # encoded, because the offset in an ISO timestamp is a "+" and a bare one is a space
    since = urlencode({"last_login_from": (now - timedelta(days=7)).isoformat()})
    found = await emails_from(api_client, since)

    # the administrator asking is in there too — they signed in a moment ago, which is the
    # column doing its job rather than a leak
    assert "recent@example.com" in found
    assert "stale@example.com" not in found
    assert "never@example.com" not in found


async def test_asking_for_the_never_barred_is_not_the_same_as_not_asking(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    await act_as(api_client, await seed_staff(session, UserRole.ADMIN))
    clean = await an_account(session, "clean@example.com")
    barred = await an_account(session, "has-history@example.com")
    # lifted, so the status is active again and only the history remembers
    session.add(AccountBlock(user_id=barred.id, reason="Старое", revoked_at=datetime.now(UTC)))
    await session.flush()

    with_history = await emails_from(api_client, "has_bans=true")
    without = await emails_from(api_client, "has_bans=false")

    assert "has-history@example.com" in with_history
    assert "clean@example.com" not in with_history
    assert "clean@example.com" in without
    assert "has-history@example.com" not in without
    assert clean.email in without


async def test_a_complaint_about_a_shop_reaches_its_owner(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    """A complaint names a shop, never a person, so the filter has to walk the ownership."""
    await act_as(api_client, await seed_staff(session, UserRole.ADMIN))
    seller = await an_account(session, "reported-seller@example.com", role=UserRole.SELLER)
    quiet = await an_account(session, "quiet-seller@example.com", role=UserRole.SELLER)
    shop = Business(
        owner_user_id=seller.id,
        legal_name="ИП Шумный",
        display_name="Шумный",
        status=BusinessStatus.ACTIVE,
    )
    session.add(shop)
    await session.flush()
    session.add(Report(business_id=shop.id, reason="Не отвечает"))
    await session.flush()

    found = await emails_from(api_client, "has_reports=true")

    assert seller.email in found
    assert quiet.email not in found


async def test_sorting_by_last_login_puts_the_silent_ones_last(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    await act_as(api_client, await seed_staff(session, UserRole.ADMIN))
    now = datetime.now(UTC)
    await an_account(session, "yesterday@example.com", last_login_at=now - timedelta(days=1))
    await an_account(session, "never-again@example.com")

    response = await api_client.get(f"{USERS_URL}?sort=last_login&limit=100")

    order = [item["email"] for item in response.json()["items"]]
    assert order.index("yesterday@example.com") < order.index("never-again@example.com")


async def test_the_count_agrees_with_what_is_listed(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    """The two go through the same narrowing, and this is what would catch them drifting."""
    await act_as(api_client, await seed_staff(session, UserRole.ADMIN))
    for index in range(3):
        await an_account(session, f"counted-{index}@example.com", role=UserRole.SELLER)

    response = await api_client.get(f"{USERS_URL}?role=seller&limit=100")

    body = response.json()
    assert body["total"] == len(body["items"])
