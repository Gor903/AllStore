import uuid

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Business,
    BusinessStatus,
    RefreshToken,
    Store,
    StoreStatus,
    User,
    UserRole,
    UserStatus,
)

pytestmark = pytest.mark.integration


def make_user(**overrides: object) -> User:
    data: dict[str, object] = {
        "email": f"user-{uuid.uuid4().hex}@example.com",
        "password_hash": "$argon2id$fake",
    }
    data.update(overrides)
    return User(**data)


async def make_business(session: AsyncSession, **overrides: object) -> Business:
    user = make_user(role=UserRole.SELLER)
    session.add(user)
    await session.flush()
    data: dict[str, object] = {
        "owner_user_id": user.id,
        "legal_name": 'ИП "Тест"',
        "display_name": "Тест",
    }
    data.update(overrides)
    business = Business(**data)
    session.add(business)
    await session.flush()
    return business


async def test_new_user_gets_buyer_role_and_active_status(session: AsyncSession) -> None:
    user = make_user()

    session.add(user)
    await session.flush()

    assert user.role is UserRole.BUYER
    assert user.status is UserStatus.ACTIVE
    assert user.email_verified_at is None
    assert isinstance(user.id, uuid.UUID)
    assert user.created_at is not None


async def test_enums_are_stored_as_lowercase_values(session: AsyncSession) -> None:
    user = make_user(role=UserRole.MODERATOR)
    session.add(user)
    await session.flush()

    stored = await session.execute(
        text("SELECT role::text FROM users WHERE id = :id"), {"id": user.id}
    )

    assert stored.scalar_one() == "moderator"


async def test_duplicate_email_is_rejected_by_the_database(session: AsyncSession) -> None:
    session.add(make_user(email="taken@example.com"))
    await session.flush()

    session.add(make_user(email="taken@example.com"))

    with pytest.raises(IntegrityError):
        await session.flush()


async def test_duplicate_phone_is_rejected(session: AsyncSession) -> None:
    session.add(make_user(phone="+37400000001"))
    await session.flush()

    session.add(make_user(phone="+37400000001"))

    with pytest.raises(IntegrityError):
        await session.flush()


async def test_phone_is_optional_for_many_users(session: AsyncSession) -> None:
    """Postgres treats NULLs as distinct — otherwise an optional phone would become mandatory."""
    session.add_all([make_user(phone=None), make_user(phone=None)])

    await session.flush()


async def test_new_business_waits_for_moderation(session: AsyncSession) -> None:
    user = make_user(role=UserRole.SELLER)
    session.add(user)
    await session.flush()

    business = Business(owner_user_id=user.id, legal_name='ИП "Тест"', display_name="Тест")
    session.add(business)
    await session.flush()

    assert business.status is BusinessStatus.PENDING


async def test_one_seller_owns_at_most_one_business(session: AsyncSession) -> None:
    user = make_user(role=UserRole.SELLER)
    session.add(user)
    await session.flush()
    session.add(Business(owner_user_id=user.id, legal_name="A", display_name="A"))
    await session.flush()

    session.add(Business(owner_user_id=user.id, legal_name="B", display_name="B"))

    with pytest.raises(IntegrityError):
        await session.flush()


async def test_new_store_starts_as_a_draft_on_the_default_theme(session: AsyncSession) -> None:
    business = await make_business(session)

    store = Store(business_id=business.id, subdomain="cups")
    session.add(store)
    await session.flush()

    assert store.status is StoreStatus.DRAFT
    assert store.theme_id == "default"
    assert store.logo_url is None
    assert store.primary_color is None
    stored = await session.execute(
        text("SELECT status::text FROM stores WHERE id = :id"), {"id": store.id}
    )
    assert stored.scalar_one() == "draft"


async def test_duplicate_subdomain_is_rejected_by_the_database(session: AsyncSession) -> None:
    first = await make_business(session)
    second = await make_business(session)
    session.add(Store(business_id=first.id, subdomain="cups"))
    await session.flush()

    session.add(Store(business_id=second.id, subdomain="cups"))

    with pytest.raises(IntegrityError):
        await session.flush()


async def test_one_business_runs_at_most_one_store(session: AsyncSession) -> None:
    business = await make_business(session)
    session.add(Store(business_id=business.id, subdomain="cups"))
    await session.flush()

    session.add(Store(business_id=business.id, subdomain="models"))

    with pytest.raises(IntegrityError):
        await session.flush()


@pytest.mark.parametrize(
    "subdomain",
    [
        "ab",  # shorter than three characters
        "-cups",  # leading hyphen
        "cups-",  # trailing hyphen
        "Cups",  # uppercase
        "my_cups",  # underscore is not a DNS label character
        "my.cups",  # a dot would add another level
        "c" * 64,  # longer than a DNS label
    ],
)
async def test_malformed_subdomain_is_rejected_by_the_database(
    session: AsyncSession, subdomain: str
) -> None:
    """The database is the backstop: no malformed tenant key reaches the table.

    The shape is rejected by the check constraint, the length by the column type — hence the
    common parent class rather than IntegrityError for every case.
    """
    business = await make_business(session)

    session.add(Store(business_id=business.id, subdomain=subdomain))

    with pytest.raises(DBAPIError):
        await session.flush()


async def test_deleting_a_business_removes_its_store(session: AsyncSession) -> None:
    business = await make_business(session)
    session.add(Store(business_id=business.id, subdomain="cups"))
    await session.flush()

    await session.execute(text("DELETE FROM businesses WHERE id = :id"), {"id": business.id})

    stores = await session.execute(select(Store).where(Store.business_id == business.id))
    assert stores.scalars().all() == []


async def test_deleting_a_user_removes_business_and_tokens(session: AsyncSession) -> None:
    user = make_user(role=UserRole.SELLER)
    session.add(user)
    await session.flush()
    session.add(Business(owner_user_id=user.id, legal_name="A", display_name="A"))
    session.add(
        RefreshToken(
            user_id=user.id,
            token_hash=uuid.uuid4().hex,
            expires_at=text("now() + interval '30 days'"),
        )
    )
    await session.flush()

    await session.execute(text("DELETE FROM users WHERE id = :id"), {"id": user.id})

    businesses = await session.execute(select(Business).where(Business.owner_user_id == user.id))
    tokens = await session.execute(select(RefreshToken).where(RefreshToken.user_id == user.id))
    assert businesses.scalars().all() == []
    assert tokens.scalars().all() == []
