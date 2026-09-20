import uuid
from decimal import Decimal

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Business,
    BusinessStatus,
    Category,
    CategoryStatus,
    ModerationStatus,
    Product,
    ProductAvailability,
    ProductImage,
    PublicationStatus,
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


async def make_category(session: AsyncSession, **overrides: object) -> Category:
    data: dict[str, object] = {"name": "Тест", "slug": f"test-{uuid.uuid4().hex}"}
    data.update(overrides)
    category = Category(**data)
    session.add(category)
    await session.flush()
    return category


async def make_product(session: AsyncSession, **overrides: object) -> Product:
    if "business_id" not in overrides:
        overrides["business_id"] = (await make_business(session)).id
    if "category_id" not in overrides:
        overrides["category_id"] = (await make_category(session)).id
    data: dict[str, object] = {"name": "Кружка", "price": Decimal("1500.00")}
    data.update(overrides)
    product = Product(**data)
    session.add(product)
    await session.flush()
    return product


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


async def test_the_migration_seeds_the_starting_catalogue(session: AsyncSession) -> None:
    """The seed rows are committed by `alembic upgrade`, so a fresh database has categories."""
    top_level = await session.execute(select(Category).where(Category.parent_id.is_(None)))
    electronics = await session.execute(select(Category).where(Category.slug == "electronics"))

    parent = electronics.scalar_one()
    children = await session.execute(select(Category).where(Category.parent_id == parent.id))
    assert len(top_level.scalars().all()) >= 8
    assert parent.status is CategoryStatus.ACTIVE
    assert "smartphones" in {child.slug for child in children.scalars()}


async def test_duplicate_category_slug_is_rejected(session: AsyncSession) -> None:
    await make_category(session, slug="cups")

    session.add(Category(name="Другая", slug="cups"))

    with pytest.raises(IntegrityError):
        await session.flush()


@pytest.mark.parametrize(
    "slug",
    [
        "Cups",  # uppercase
        "my cups",  # space
        "my_cups",  # underscore
        "-cups",  # leading hyphen
        "cups-",  # trailing hyphen
        "my--cups",  # doubled hyphen
        "",  # empty
    ],
)
async def test_malformed_category_slug_is_rejected_by_the_database(
    session: AsyncSession, slug: str
) -> None:
    session.add(Category(name="Тест", slug=slug))

    with pytest.raises(IntegrityError):
        await session.flush()


async def test_deleting_a_parent_category_removes_its_children(session: AsyncSession) -> None:
    parent = await make_category(session)
    child = await make_category(session, parent_id=parent.id)

    await session.execute(text("DELETE FROM categories WHERE id = :id"), {"id": parent.id})

    remaining = await session.execute(select(Category).where(Category.id == child.id))
    assert remaining.scalars().all() == []


async def test_new_product_waits_for_moderation_and_stays_unpublished(
    session: AsyncSession,
) -> None:
    product = await make_product(session)

    assert product.moderation_status is ModerationStatus.PENDING
    assert product.publication_status is PublicationStatus.DRAFT
    assert product.availability_status is ProductAvailability.IN_STOCK
    assert product.currency == "AMD"
    assert product.stock_quantity == 0


async def test_product_enums_are_stored_as_lowercase_values(session: AsyncSession) -> None:
    product = await make_product(session, moderation_status=ModerationStatus.APPROVED)

    stored = await session.execute(
        text(
            "SELECT moderation_status::text, publication_status::text FROM products WHERE id = :id"
        ),
        {"id": product.id},
    )

    assert stored.one() == ("approved", "draft")


async def test_price_keeps_its_minor_units(session: AsyncSession) -> None:
    """Numeric, not float: 19999.99 must come back as it went in, to the last lepton."""
    product = await make_product(session, price=Decimal("19999.99"))

    stored = await session.execute(select(Product.price).where(Product.id == product.id))

    assert stored.scalar_one() == Decimal("19999.99")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("price", Decimal("-1.00")),  # a negative price
        ("stock_quantity", -1),  # a negative stock
        ("currency", "amd"),  # not an ISO 4217 code
        ("currency", "DRAM"),  # longer than three characters
    ],
)
async def test_malformed_product_values_are_rejected_by_the_database(
    session: AsyncSession, field: str, value: object
) -> None:
    business = await make_business(session)
    category = await make_category(session)

    session.add(
        Product(
            business_id=business.id,
            category_id=category.id,
            name="Кружка",
            **{"price": Decimal("1500.00"), field: value},
        )
    )

    with pytest.raises(DBAPIError):
        await session.flush()


async def test_a_category_in_use_cannot_be_deleted(session: AsyncSession) -> None:
    """RESTRICT, not CASCADE: removing a category must never take products down with it."""
    category = await make_category(session)
    await make_product(session, category_id=category.id)

    with pytest.raises(IntegrityError):
        await session.execute(text("DELETE FROM categories WHERE id = :id"), {"id": category.id})


async def test_deleting_a_business_removes_its_products(session: AsyncSession) -> None:
    business = await make_business(session)
    product = await make_product(session, business_id=business.id)

    await session.execute(text("DELETE FROM businesses WHERE id = :id"), {"id": business.id})

    remaining = await session.execute(select(Product).where(Product.id == product.id))
    assert remaining.scalars().all() == []


async def test_deleting_a_product_removes_its_images(session: AsyncSession) -> None:
    product = await make_product(session)
    session.add(ProductImage(product_id=product.id, image_url="https://cdn/1.jpg"))
    await session.flush()

    await session.execute(text("DELETE FROM products WHERE id = :id"), {"id": product.id})

    images = await session.execute(
        select(ProductImage).where(ProductImage.product_id == product.id)
    )
    assert images.scalars().all() == []


async def test_images_are_read_back_in_gallery_order(session: AsyncSession) -> None:
    product = await make_product(session)
    session.add_all(
        [
            ProductImage(product_id=product.id, image_url="https://cdn/second.jpg", sort_order=2),
            ProductImage(product_id=product.id, image_url="https://cdn/cover.jpg", sort_order=0),
        ]
    )
    await session.flush()

    await session.refresh(product, attribute_names=["images"])

    assert [image.sort_order for image in product.images] == [0, 2]


async def test_negative_sort_order_is_rejected(session: AsyncSession) -> None:
    product = await make_product(session)

    session.add(ProductImage(product_id=product.id, image_url="https://cdn/1.jpg", sort_order=-1))

    with pytest.raises(IntegrityError):
        await session.flush()
