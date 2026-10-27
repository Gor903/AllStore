import uuid
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import (
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    ValidationFailedError,
)
from app.models import Business, BusinessStatus, Store, StoreStatus
from app.repositories import stores
from app.services import customer_blocks

SUBDOMAIN_INDEX = "ix_stores_subdomain"


class SubdomainReservedError(ValidationFailedError):
    code = "subdomain_reserved"


class SubdomainTakenError(ConflictError):
    code = "subdomain_taken"


class StoreAlreadyExistsError(ConflictError):
    code = "store_already_exists"


class BusinessNotEligibleError(PermissionDeniedError):
    code = "business_not_eligible"


def _on_subdomain(message: str) -> list[dict[str, Any]]:
    """The shape FastAPI uses for validation errors, so the frontend files it under the field."""
    return [{"loc": ["body", "subdomain"], "msg": message}]


async def create_store(
    session: AsyncSession, settings: Settings, business: Business, subdomain: str
) -> Store:
    if business.status in (BusinessStatus.SUSPENDED, BusinessStatus.BLOCKED):
        raise BusinessNotEligibleError("Бизнес заблокирован, витрину создать нельзя")
    if await stores.get_by_business(session, business.id) is not None:
        raise StoreAlreadyExistsError("У этого бизнеса уже есть витрина")
    if subdomain in settings.reserved_subdomains:
        raise SubdomainReservedError(
            "Этот адрес зарезервирован, выберите другой",
            details=_on_subdomain("Адрес зарезервирован"),
        )
    if await stores.get_by_subdomain(session, subdomain) is not None:
        raise _subdomain_taken()

    # a storefront of an already admitted business goes live at once: nothing is left to
    # check, and a draft here would wait for a moderation event that will never come
    status = StoreStatus.ACTIVE if business.status is BusinessStatus.ACTIVE else StoreStatus.DRAFT
    try:
        return await stores.add(
            session, Store(business_id=business.id, subdomain=subdomain, status=status)
        )
    except IntegrityError as exc:
        # two sellers can clear the check above in the same moment; the unique index settles it
        if SUBDOMAIN_INDEX not in str(exc.orig):
            raise
        raise _subdomain_taken() from exc


def is_public(store: Store) -> bool:
    """A storefront goes public only once a moderator has approved the business behind it,
    and stays public only while the person who owns it is in good standing.

    The DRAFT → ACTIVE transition belongs to moderation (этап 5); until then a created
    storefront resolves to nothing, which is what PR1 reserved the draft status for. The
    owner's status is the third condition, and the same one the catalogue filters on: barring
    a seller takes their shelf down with them rather than leaving it selling.
    """
    return (
        store.status is StoreStatus.ACTIVE
        and store.business.status is BusinessStatus.ACTIVE
        and store.business.owner.is_active
    )


async def get_public_store(
    session: AsyncSession, subdomain: str, viewer_id: uuid.UUID | None = None
) -> Store:
    """Missing and not-yet-public storefronts answer the same: 404 tells the visitor nothing.

    A buyer this shop has barred is a different case and gets a different answer: they know
    the shop is there, so 403 with a reason beats a riddle. See services/customer_blocks.py.
    """
    store = await stores.get_with_business_by_subdomain(session, subdomain)
    if store is None or not is_public(store):
        raise NotFoundError("Магазин не найден")
    await customer_blocks.ensure_may_see(session, store.business_id, viewer_id)
    return store


def _subdomain_taken() -> SubdomainTakenError:
    return SubdomainTakenError(
        "Этот адрес уже занят, выберите другой", details=_on_subdomain("Адрес занят")
    )
