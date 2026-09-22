"""Complaints: how one is filed, and how a moderator closes it.

A complaint is about a thing, not about a sentence someone wrote. So the queue groups by
subject and a verdict closes every open complaint about that subject at once — otherwise
a moderator would hide a product and still face nineteen lines about the same product.

Upholding a complaint goes through the moderation the platform already has: hiding a
product and suspending a shop are the same operations the queue performs, with the same
entries in the moderation history. Nothing new decides anyone's fate here.
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, NotFoundError
from app.models import Business, Product, Report, ReportStatus, User
from app.repositories import reports as reports_repo
from app.repositories.reports import OpenSubject
from app.services import business_moderation, moderation_queue


class ReportSubjectNotFoundError(NotFoundError):
    code = "report_subject_not_found"


class NothingToResolveError(ConflictError):
    code = "no_open_reports"


async def report_product(
    session: AsyncSession, reporter: User | None, product_id: uuid.UUID, reason: str
) -> Report:
    await _public_product(session, product_id)
    return await _file(session, reporter, product_id=product_id, business_id=None, reason=reason)


async def report_shop(
    session: AsyncSession, reporter: User | None, subdomain: str, reason: str
) -> Report:
    business_id = await reports_repo.live_business_by_subdomain(session, subdomain)
    if business_id is None:
        raise ReportSubjectNotFoundError("Магазин не найден")
    return await _file(session, reporter, product_id=None, business_id=business_id, reason=reason)


async def list_queue(
    session: AsyncSession, limit: int, offset: int
) -> tuple[list[OpenSubject], dict[uuid.UUID, Product], dict[uuid.UUID, Business], int]:
    subjects = await reports_repo.list_open_subjects(session, limit, offset)
    products = await reports_repo.load_products(
        session, [s.product_id for s in subjects if s.product_id is not None]
    )
    businesses = await reports_repo.load_businesses(
        session, [s.business_id for s in subjects if s.business_id is not None]
    )
    return subjects, products, businesses, await reports_repo.count_open_subjects(session)


async def uphold_product(
    session: AsyncSession, moderator: User, product_id: uuid.UUID, reason: str
) -> int:
    """The complaint was right: the product comes off the shelf through moderation, so the
    seller sees it in the same history as any other verdict."""
    closed = await _close(
        session, moderator, product_id=product_id, business_id=None, status=ReportStatus.UPHELD
    )
    await moderation_queue.hide(session, moderator, product_id)
    return closed


async def uphold_business(
    session: AsyncSession, moderator: User, business_id: uuid.UUID, reason: str
) -> int:
    closed = await _close(
        session, moderator, product_id=None, business_id=business_id, status=ReportStatus.UPHELD
    )
    await business_moderation.suspend(session, moderator, business_id, reason)
    return closed


async def dismiss_product(
    session: AsyncSession, moderator: User, product_id: uuid.UUID, reason: str
) -> int:
    return await _close(
        session,
        moderator,
        product_id=product_id,
        business_id=None,
        status=ReportStatus.DISMISSED,
        reason=reason,
    )


async def dismiss_business(
    session: AsyncSession, moderator: User, business_id: uuid.UUID, reason: str
) -> int:
    return await _close(
        session,
        moderator,
        product_id=None,
        business_id=business_id,
        status=ReportStatus.DISMISSED,
        reason=reason,
    )


async def _file(
    session: AsyncSession,
    reporter: User | None,
    *,
    product_id: uuid.UUID | None,
    business_id: uuid.UUID | None,
    reason: str,
) -> Report:
    if reporter is not None:
        # the same person clicking twice is one complaint, not two
        existing = await reports_repo.open_report_of(session, reporter.id, product_id, business_id)
        if existing is not None:
            return existing

    return await reports_repo.add(
        session,
        Report(
            reporter_user_id=None if reporter is None else reporter.id,
            product_id=product_id,
            business_id=business_id,
            reason=reason,
        ),
    )


async def _close(
    session: AsyncSession,
    moderator: User,
    *,
    product_id: uuid.UUID | None,
    business_id: uuid.UUID | None,
    status: ReportStatus,
    reason: str | None = None,
) -> int:
    closed = await reports_repo.close_subject(
        session,
        product_id=product_id,
        business_id=business_id,
        status=status,
        moderator_id=moderator.id,
        reason=reason,
    )
    if closed == 0:
        raise NothingToResolveError("По этому предмету нет открытых жалоб")
    return closed


async def _public_product(session: AsyncSession, product_id: uuid.UUID) -> None:
    if not await reports_repo.public_product_exists(session, product_id):
        raise ReportSubjectNotFoundError("Товар не найден")
