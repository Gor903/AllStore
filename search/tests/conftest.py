import os
import uuid
from collections.abc import AsyncIterator

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

# defaults let the suite run with no shell setup; CI overrides them via env
_DEFAULTS = {
    "DATABASE_URL": "postgresql+asyncpg://allstore:allstore@localhost:5433/allstore_test",
    "EMBEDDER": "fake",
}
for key, value in _DEFAULTS.items():
    os.environ.setdefault(key, value)

from app.config import get_settings  # noqa: E402
from app.embedder import FakeEmbedder  # noqa: E402


@pytest.fixture
def embedder() -> FakeEmbedder:
    return FakeEmbedder(get_settings().embedding_dimensions)


@pytest.fixture
async def session() -> AsyncIterator[AsyncSession]:
    """A session inside a transaction that is rolled back — the database stays as it was."""
    engine = create_async_engine(str(get_settings().database_url))
    async with engine.connect() as connection:
        transaction = await connection.begin()
        async with AsyncSession(bind=connection, expire_on_commit=False) as opened:
            yield opened
        await transaction.rollback()
    await engine.dispose()


@pytest.fixture
async def product(session: AsyncSession) -> uuid.UUID:
    """A published product with a shop and a category, built with plain SQL.

    The service owns no models of its own beyond the narrow mirror, so a fixture that builds
    its neighbours through the ORM would be inventing a dependency the service does not have.
    """
    suffix = uuid.uuid4().hex[:8]
    user_id, business_id, category_id, product_id = (uuid.uuid4() for _ in range(4))
    await session.execute(
        text(
            "insert into users (id, email, password_hash, role, status, created_at, updated_at)"
            " values (:id, :email, 'x', 'seller', 'active', now(), now())"
        ),
        {"id": user_id, "email": f"seller-{suffix}@example.com"},
    )
    await session.execute(
        text(
            "insert into businesses (id, owner_user_id, legal_name, display_name, status,"
            " created_at, updated_at)"
            " values (:id, :owner, 'ИП Тест', 'Гончарная лавка', 'active', now(), now())"
        ),
        {"id": business_id, "owner": user_id},
    )
    await session.execute(
        text(
            "insert into categories (id, slug, name, status, created_at, updated_at)"
            " values (:id, :slug, 'Посуда', 'active', now(), now())"
        ),
        {"id": category_id, "slug": f"dishes-{suffix}"},
    )
    await session.execute(
        text(
            "insert into products (id, business_id, category_id, name, description, price,"
            " currency, stock_quantity, availability_status, moderation_status,"
            " publication_status, created_at, updated_at)"
            " values (:id, :business, :category, 'Ваза «Гюмри»', 'Керамика ручной работы',"
            " 12500, 'AMD', 3, 'in_stock', 'approved', 'published', now(), now())"
        ),
        {"id": product_id, "business": business_id, "category": category_id},
    )
    return product_id
