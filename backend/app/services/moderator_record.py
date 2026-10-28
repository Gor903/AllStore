"""What one moderator has done, counted and listed.

The administrator's window on the people who run the platform. Every number here is read
from the record the action itself left behind — verdicts from the review tables, bans from
`account_blocks`, everything else from the journal — rather than from a tally kept beside
them. A counter maintained in parallel is a counter that can be wrong, and a wrong one here
would be worse than none: it would be read as evidence.
"""

import uuid
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.models import (
    AccountBlock,
    BusinessDecision,
    BusinessModerationReview,
    ModerationDecision,
    ModerationReview,
    User,
    UserRole,
)
from app.repositories import users as users_repo


class NotAModeratorError(NotFoundError):
    """Said as "no such thing" rather than "not allowed": an account that is not a moderator
    has no record to show, and whether it exists at all is not this screen's business."""

    code = "moderator_not_found"


@dataclass(frozen=True)
class ModeratorRecord:
    moderator: User
    products_approved: int
    products_rejected: int
    businesses_approved: int
    businesses_refused: int
    accounts_blocked: int


async def find_moderator(session: AsyncSession, user_id: uuid.UUID) -> User:
    user = await users_repo.get_by_id(session, user_id)
    if user is None or user.role is not UserRole.MODERATOR:
        raise NotAModeratorError("Модератор не найден")
    return user


async def record_of(session: AsyncSession, user_id: uuid.UUID) -> ModeratorRecord:
    moderator = await find_moderator(session, user_id)
    return ModeratorRecord(
        moderator=moderator,
        products_approved=await _count_products(session, user_id, ModerationDecision.APPROVED),
        products_rejected=await _count_products(session, user_id, ModerationDecision.REJECTED),
        businesses_approved=await _count_businesses(session, user_id, BusinessDecision.APPROVED),
        businesses_refused=await _count_businesses(session, user_id, BusinessDecision.REJECTED),
        accounts_blocked=await _count_blocks(session, user_id),
    )


async def _count_products(
    session: AsyncSession, user_id: uuid.UUID, decision: ModerationDecision
) -> int:
    result = await session.execute(
        select(func.count())
        .select_from(ModerationReview)
        .where(
            ModerationReview.moderator_id == user_id,
            ModerationReview.decision == decision,
        )
    )
    return result.scalar_one()


async def _count_businesses(
    session: AsyncSession, user_id: uuid.UUID, decision: BusinessDecision
) -> int:
    result = await session.execute(
        select(func.count())
        .select_from(BusinessModerationReview)
        .where(
            BusinessModerationReview.moderator_id == user_id,
            BusinessModerationReview.decision == decision,
        )
    )
    return result.scalar_one()


async def _count_blocks(session: AsyncSession, user_id: uuid.UUID) -> int:
    """Every ban they ever laid, including the ones since lifted: the question is what this
    moderator did, not what is still in force."""
    result = await session.execute(
        select(func.count()).select_from(AccountBlock).where(AccountBlock.actor_user_id == user_id)
    )
    return result.scalar_one()
