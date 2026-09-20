"""Admission of a seller to the platform, and the only place a business status moves.

    pending ──approve──> active ──suspend──> suspended ──restore──> active
    any except blocked ──block──> blocked ──restore──> active

The storefront follows the business that runs it: there is no case where one is barred and
the other is on the air.
"""

import uuid
from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.models import (
    Business,
    BusinessDecision,
    BusinessModerationReview,
    BusinessStatus,
    StoreStatus,
    User,
)
from app.repositories import businesses as businesses_repo
from app.services.moderation import InvalidTransitionError

STORE_STATUS_OF = {
    BusinessStatus.ACTIVE: StoreStatus.ACTIVE,
    BusinessStatus.SUSPENDED: StoreStatus.SUSPENDED,
    BusinessStatus.BLOCKED: StoreStatus.BLOCKED,
}


class BusinessNotFoundError(NotFoundError):
    code = "business_not_found"


async def list_pending(
    session: AsyncSession, limit: int, offset: int
) -> tuple[Sequence[Business], int]:
    return (
        await businesses_repo.list_pending(session, limit, offset),
        await businesses_repo.count_pending(session),
    )


async def approve(session: AsyncSession, moderator: User, business_id: uuid.UUID) -> Business:
    """Admission: from here the storefront answers on its subdomain."""
    business = await _find(session, business_id)
    _require(business.status is BusinessStatus.PENDING, "Одобрить можно только бизнес на проверке")
    _move(business, BusinessStatus.ACTIVE)
    await _record(session, business, moderator, BusinessDecision.APPROVED, None)
    return business


async def suspend(
    session: AsyncSession, moderator: User, business_id: uuid.UUID, reason: str
) -> Business:
    business = await _find(session, business_id)
    _require(
        business.status is BusinessStatus.ACTIVE, "Приостановить можно только действующий бизнес"
    )
    _move(business, BusinessStatus.SUSPENDED)
    await _record(session, business, moderator, BusinessDecision.SUSPENDED, reason)
    return business


async def block(
    session: AsyncSession, moderator: User, business_id: uuid.UUID, reason: str
) -> Business:
    business = await _find(session, business_id)
    _require(business.status is not BusinessStatus.BLOCKED, "Бизнес уже заблокирован")
    _move(business, BusinessStatus.BLOCKED)
    await _record(session, business, moderator, BusinessDecision.BLOCKED, reason)
    return business


async def restore(session: AsyncSession, moderator: User, business_id: uuid.UUID) -> Business:
    """A ban is a status, not a deletion, so it can be taken back."""
    business = await _find(session, business_id)
    _require(
        business.status in (BusinessStatus.SUSPENDED, BusinessStatus.BLOCKED),
        "Восстанавливать нечего: бизнес не приостановлен и не заблокирован",
    )
    _move(business, BusinessStatus.ACTIVE)
    await _record(session, business, moderator, BusinessDecision.RESTORED, None)
    return business


def _move(business: Business, status: BusinessStatus) -> None:
    business.status = status
    if business.store is not None:
        business.store.status = STORE_STATUS_OF[status]


async def _find(session: AsyncSession, business_id: uuid.UUID) -> Business:
    business = await businesses_repo.get_with_store(session, business_id)
    if business is None:
        raise BusinessNotFoundError("Бизнес не найден")
    return business


async def _record(
    session: AsyncSession,
    business: Business,
    moderator: User,
    decision: BusinessDecision,
    reason: str | None,
) -> None:
    await businesses_repo.add_review(
        session,
        BusinessModerationReview(
            business_id=business.id,
            moderator_id=moderator.id,
            decision=decision,
            reason=reason,
        ),
    )
    await session.refresh(business, attribute_names=["reviews", "updated_at"])


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise InvalidTransitionError(message)
