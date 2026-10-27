import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError, PermissionDeniedError, ValidationFailedError
from app.models import (
    Business,
    BusinessStatus,
    Category,
    ModerationStatus,
    Product,
    ProductRevision,
)
from app.repositories import categories, products
from app.repositories import product_revisions as revisions_repo
from app.schemas.product import ProductCreateRequest, ProductUpdateRequest
from app.services import contacts, moderation

# what a moderator judged; changing any of it invalidates the verdict, price and stock do not
MODERATED_FIELDS = frozenset({"name", "description", "category_id"})

# A shop may fill its shelves while it waits to be admitted — nothing is public until a
# moderator says so, and a seller who cannot prepare anything has nothing to be admitted for.
# Once refused, suspended or barred it may not: queueing new goods would be a way of
# outlasting the verdict rather than answering it.
TRADING_STATUSES = frozenset({BusinessStatus.PENDING, BusinessStatus.ACTIVE})


class ProductNotFoundError(NotFoundError):
    code = "product_not_found"


class CategoryNotFoundError(ValidationFailedError):
    code = "category_not_found"


class BusinessNotTradingError(PermissionDeniedError):
    code = "business_not_trading"


async def create_product(
    session: AsyncSession, business: Business, payload: ProductCreateRequest
) -> Product:
    require_trading(business)
    await resolve_category(session, payload.category_id)
    # creating a product already files it into the queue, so the contact is required here
    # and not only at submit — otherwise the rule would be bypassed by never resubmitting
    await contacts.require_contact(session, business.id)
    # moderation and publication keep their model defaults: pending and draft, so the
    # product is invisible to buyers until a moderator has approved it
    product = await products.add(session, Product(business_id=business.id, **payload.model_dump()))
    # the first proposal is the product itself: a moderator judges a revision, and a product
    # without one would sit in no queue at all
    await _propose(session, product, {})
    # the collections have to be loaded: the response carries them, and a lazy load in the
    # async session would have nowhere to run
    await session.refresh(product, attribute_names=["images", "reviews", "revisions"])
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
    business: Business,
    product_id: uuid.UUID,
    payload: ProductUpdateRequest,
) -> Product:
    """Price and stock change at once; name, description and category are proposed.

    The split is what keeps a live listing live. A buyer goes on seeing the approved text
    while the new one waits, so fixing a typo no longer costs the seller their place on the
    shelf for as long as the queue takes.
    """
    product = await get_owned_product(session, business.id, product_id)
    changes: dict[str, Any] = payload.model_dump(exclude_unset=True)
    proposed = {field: changes[field] for field in MODERATED_FIELDS & changes.keys()}

    for field, value in changes.items():
        if field not in MODERATED_FIELDS:
            setattr(product, field, value)
    if proposed:
        if "category_id" in proposed:
            await resolve_category(session, proposed["category_id"])
        require_trading(business)
        await contacts.require_contact(session, business.id)
        await _propose(session, product, proposed)

    await session.flush()
    # updated_at is computed by the database on UPDATE, so the column comes back expired
    await session.refresh(product, attribute_names=["revisions", "updated_at"])
    return product


async def submit_product_for_review(
    session: AsyncSession, business: Business, product_id: uuid.UUID
) -> Product:
    """Puts the product in front of a moderator again without changing a word of it.

    Editing already does that by itself, so what is left for this is everything moderation
    looks at that is not a moderated field — the photographs, above all. A seller who
    replaced the picture that got them refused has nothing to retype and still needs a way
    to ask again.
    """
    product = await get_owned_product(session, business.id, product_id)
    require_trading(business)
    await contacts.require_contact(session, business.id)
    if product.pending_revision is not None:
        raise moderation.InvalidTransitionError("Товар уже на проверке")

    await _propose(session, product, {})
    await session.flush()
    await session.refresh(product, attribute_names=["revisions", "updated_at"])
    return product


async def _propose(
    session: AsyncSession, product: Product, changes: dict[str, Any]
) -> ProductRevision:
    """Files a proposal, built on whatever is already waiting rather than on the shelf.

    Editing twice before a moderator gets to it must leave one proposal carrying both edits,
    not a second one that silently drops the first. The earlier proposal is superseded — kept,
    never deleted, because what a shop tried to publish is part of its record.
    """
    # asked of the database rather than of the loaded collection: a product created a
    # moment ago has no collection to speak of, and a stale one would silently queue a
    # second proposal beside the first
    pending = await revisions_repo.get_pending(session, product.id)
    base = pending or product
    if pending is not None:
        moderation.supersede(pending)

    revision = await revisions_repo.add(
        session,
        ProductRevision(
            product_id=product.id,
            name=changes.get("name", base.name),
            description=changes.get("description", base.description),
            category_id=changes.get("category_id", base.category_id),
        ),
    )
    if product.moderation_status is not ModerationStatus.APPROVED:
        # nothing of this product is public, so there is no old version to protect: the
        # cabinet shows what the seller just typed rather than what they typed yesterday
        product.name = revision.name
        product.description = revision.description
        product.category_id = revision.category_id
        product.moderation_status = ModerationStatus.PENDING
    return revision


def require_trading(business: Business) -> None:
    """A shop under a verdict does not add to the queue.

    Not a silent no-op and not a 404: the seller is told, because what they have to do about
    it — answer the refusal, wait out the suspension — is a different thing in each case.
    """
    if business.status not in TRADING_STATUSES:
        raise BusinessNotTradingError(
            "Магазин под решением модератора: новые товары на проверку сейчас не принимаются"
        )


async def archive_product(
    session: AsyncSession, business_id: uuid.UUID, product_id: uuid.UUID
) -> None:
    product = await get_owned_product(session, business_id, product_id)
    product.archived_at = datetime.now(UTC)
    # belt and braces: even a public query that forgets archived_at must not surface it
    moderation.withdraw(product)
    pending = product.pending_revision
    if pending is not None:
        # a proposal for a product nobody sells any more is not something to judge
        moderation.supersede(pending)
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
