import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError, ValidationFailedError
from app.models import (
    Business,
    Category,
    ModerationStatus,
    Product,
)
from app.repositories import categories, products
from app.schemas.product import ProductCreateRequest, ProductUpdateRequest
from app.services import moderation

# what a moderator judged; changing any of it invalidates the verdict, price and stock do not
MODERATED_FIELDS = frozenset({"name", "description", "category_id"})


class ProductNotFoundError(NotFoundError):
    code = "product_not_found"


class CategoryNotFoundError(ValidationFailedError):
    code = "category_not_found"


async def create_product(
    session: AsyncSession, business: Business, payload: ProductCreateRequest
) -> Product:
    await resolve_category(session, payload.category_id)
    # moderation and publication keep their model defaults: pending and draft, so the
    # product is invisible to buyers until a moderator has approved it
    product = await products.add(session, Product(business_id=business.id, **payload.model_dump()))
    # both collections are empty but have to be loaded: the response carries them, and a
    # lazy load in the async session would have nowhere to run
    await session.refresh(product, attribute_names=["images", "reviews"])
    return product


async def get_owned_product(
    session: AsyncSession, business_id: uuid.UUID, product_id: uuid.UUID
) -> Product:
    """A product of another business answers 404, not 403: its existence is not ours to reveal."""
    product = await products.get_owned(session, business_id, product_id)
    if product is None:
        raise ProductNotFoundError("Товар не найден")
    return product


async def update_product(
    session: AsyncSession,
    business_id: uuid.UUID,
    product_id: uuid.UUID,
    payload: ProductUpdateRequest,
) -> Product:
    product = await get_owned_product(session, business_id, product_id)
    changes: dict[str, Any] = payload.model_dump(exclude_unset=True)
    if "category_id" in changes:
        await resolve_category(session, changes["category_id"])

    for field, value in changes.items():
        setattr(product, field, value)
    if MODERATED_FIELDS & changes.keys() and product.moderation_status is ModerationStatus.APPROVED:
        # the approved product is not the one on the shelf any more — back into the queue
        moderation.submit_for_review(product)

    await session.flush()
    # updated_at is computed by the database on UPDATE, so the column comes back expired
    await session.refresh(product, attribute_names=["updated_at"])
    return product


async def submit_product_for_review(
    session: AsyncSession, business_id: uuid.UUID, product_id: uuid.UUID
) -> Product:
    """The seller sends a refused — or an already approved — product back into the queue."""
    product = await get_owned_product(session, business_id, product_id)
    moderation.submit_for_review(product)
    await session.flush()
    await session.refresh(product, attribute_names=["updated_at"])
    return product


async def archive_product(
    session: AsyncSession, business_id: uuid.UUID, product_id: uuid.UUID
) -> None:
    product = await get_owned_product(session, business_id, product_id)
    product.archived_at = datetime.now(UTC)
    # belt and braces: even a public query that forgets archived_at must not surface it
    moderation.withdraw(product)
    await session.flush()


async def resolve_category(session: AsyncSession, category_id: uuid.UUID) -> Category:
    category = await categories.get_active_by_id(session, category_id)
    if category is None:
        raise CategoryNotFoundError(
            "Категория не найдена",
            # the shape FastAPI uses, so the frontend files it under the field
            details=[{"loc": ["body", "category_id"], "msg": "Категория не найдена"}],
        )
    return category
