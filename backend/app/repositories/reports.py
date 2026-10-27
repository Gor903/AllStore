import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any, NamedTuple

from sqlalchemy import CursorResult, func, select, update
from sqlalchemy.dialects.postgresql import aggregate_order_by
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import (
    Business,
    Product,
    ProductRevision,
    Report,
    ReportStatus,
    Store,
)
from app.repositories.catalog import PUBLIC_PRODUCT, PUBLIC_STORE, with_public_joins

# how many complaints a moderator is shown per subject: enough to see a pattern, not a wall
REASONS_SHOWN = 5


class OpenSubject(NamedTuple):
    """One line of the queue: a subject and everything said about it."""

    product_id: uuid.UUID | None
    business_id: uuid.UUID | None
    total: int
    last_at: datetime
    reasons: list[str]


async def add(session: AsyncSession, report: Report) -> Report:
    session.add(report)
    await session.flush()
    return report


async def open_report_of(
    session: AsyncSession,
    reporter_user_id: uuid.UUID,
    product_id: uuid.UUID | None,
    business_id: uuid.UUID | None,
) -> Report | None:
    """The same person complaining twice about the same thing is one complaint."""
    result = await session.execute(
        select(Report).where(
            Report.reporter_user_id == reporter_user_id,
            Report.status == ReportStatus.OPEN,
            Report.product_id == product_id,
            Report.business_id == business_id,
        )
    )
    return result.scalars().first()


def _grouped() -> Any:
    return (
        select(
            Report.product_id,
            Report.business_id,
            func.count().label("total"),
            func.max(Report.created_at).label("last_at"),
            func.array_agg(aggregate_order_by(Report.reason, Report.created_at.desc())).label(
                "reasons"
            ),
        )
        .where(Report.status == ReportStatus.OPEN)
        .group_by(Report.product_id, Report.business_id)
    )


async def list_open_subjects(session: AsyncSession, limit: int, offset: int) -> list[OpenSubject]:
    """Grouped by subject: twenty people reporting one product is one line, not twenty."""
    result = await session.execute(
        _grouped().order_by(func.max(Report.created_at).desc()).limit(limit).offset(offset)
    )
    return [
        OpenSubject(
            product_id=row.product_id,
            business_id=row.business_id,
            total=row.total,
            last_at=row.last_at,
            reasons=list(row.reasons[:REASONS_SHOWN]),
        )
        for row in result.all()
    ]


async def count_open_subjects(session: AsyncSession) -> int:
    result = await session.execute(select(func.count()).select_from(_grouped().subquery()))
    return result.scalar_one()


async def load_products(
    session: AsyncSession, ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, Product]:
    if not ids:
        return {}
    result = await session.execute(
        select(Product)
        .options(
            selectinload(Product.images),
            selectinload(Product.reviews),
            selectinload(Product.category),
            selectinload(Product.revisions).selectinload(ProductRevision.category),
            selectinload(Product.business).selectinload(Business.store),
        )
        .where(Product.id.in_(ids))
    )
    return {product.id: product for product in result.unique().scalars().all()}


async def load_businesses(
    session: AsyncSession, ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, Business]:
    if not ids:
        return {}
    result = await session.execute(
        select(Business).options(selectinload(Business.store)).where(Business.id.in_(ids))
    )
    return {business.id: business for business in result.unique().scalars().all()}


async def close_subject(
    session: AsyncSession,
    *,
    product_id: uuid.UUID | None,
    business_id: uuid.UUID | None,
    status: ReportStatus,
    moderator_id: uuid.UUID,
    reason: str | None,
) -> int:
    """Closes every open complaint about the subject at once: the moderator judged the
    thing, not one person's sentence about it. Answers with how many were closed."""
    result = await session.execute(
        update(Report)
        .where(
            Report.status == ReportStatus.OPEN,
            Report.product_id == product_id,
            Report.business_id == business_id,
        )
        .values(
            status=status,
            resolved_by=moderator_id,
            resolution_reason=reason,
            resolved_at=datetime.now(UTC),
        )
    )
    await session.flush()
    return CursorResult.rowcount.fget(result)


async def public_product_exists(session: AsyncSession, product_id: uuid.UUID) -> bool:
    """Only what a visitor can actually see may be complained about. Anything else is
    either already off the shelf or never existed, and both answer the same."""
    result = await session.execute(
        with_public_joins(select(Product.id)).where(Product.id == product_id, *PUBLIC_PRODUCT)
    )
    return result.scalar_one_or_none() is not None


async def live_business_by_subdomain(session: AsyncSession, subdomain: str) -> uuid.UUID | None:
    """Only a shop on the air can be complained about, and it is named the way a visitor
    sees it — by the address in their browser."""
    result = await session.execute(
        select(Business.id)
        .join(Business.store)
        .join(Business.owner)
        .where(Store.subdomain == subdomain, *PUBLIC_STORE)
    )
    return result.scalar_one_or_none()
