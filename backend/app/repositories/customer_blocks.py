import uuid
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import BusinessCustomerBlock


async def add(session: AsyncSession, block: BusinessCustomerBlock) -> BusinessCustomerBlock:
    session.add(block)
    await session.flush()
    return block


async def get(session: AsyncSession, block_id: uuid.UUID) -> BusinessCustomerBlock | None:
    return await session.get(BusinessCustomerBlock, block_id)


async def get_in_force(
    session: AsyncSession, business_id: uuid.UUID, buyer_user_id: uuid.UUID
) -> BusinessCustomerBlock | None:
    """At most one exists per pair: a unique partial index on `revoked_at IS NULL` says so."""
    result = await session.execute(
        select(BusinessCustomerBlock).where(
            BusinessCustomerBlock.business_id == business_id,
            BusinessCustomerBlock.buyer_user_id == buyer_user_id,
            BusinessCustomerBlock.revoked_at.is_(None),
        )
    )
    return result.scalar_one_or_none()


async def is_blocked(
    session: AsyncSession, business_id: uuid.UUID, buyer_user_id: uuid.UUID | None
) -> bool:
    if buyer_user_id is None:
        return False
    return await get_in_force(session, business_id, buyer_user_id) is not None


async def list_for_business(
    session: AsyncSession, business_id: uuid.UUID, limit: int, offset: int
) -> tuple[Sequence[BusinessCustomerBlock], int]:
    """Newest first, lifted ones included: a shop keeps the record of who it barred and when."""
    rows = await session.execute(
        select(BusinessCustomerBlock)
        .options(
            selectinload(BusinessCustomerBlock.buyer),
            selectinload(BusinessCustomerBlock.revoked_by),
        )
        .where(BusinessCustomerBlock.business_id == business_id)
        .order_by(BusinessCustomerBlock.created_at.desc(), BusinessCustomerBlock.id)
        .limit(limit)
        .offset(offset)
    )
    total = await session.execute(
        select(func.count())
        .select_from(BusinessCustomerBlock)
        .where(BusinessCustomerBlock.business_id == business_id)
    )
    return rows.scalars().all(), total.scalar_one()


async def list_for_buyer(
    session: AsyncSession, buyer_user_id: uuid.UUID, limit: int, offset: int
) -> tuple[Sequence[BusinessCustomerBlock], int]:
    """The other direction, for the staff screens: which shops have barred this person."""
    rows = await session.execute(
        select(BusinessCustomerBlock)
        .options(
            selectinload(BusinessCustomerBlock.business),
            selectinload(BusinessCustomerBlock.buyer),
            selectinload(BusinessCustomerBlock.revoked_by),
        )
        .where(BusinessCustomerBlock.buyer_user_id == buyer_user_id)
        .order_by(BusinessCustomerBlock.created_at.desc(), BusinessCustomerBlock.id)
        .limit(limit)
        .offset(offset)
    )
    total = await session.execute(
        select(func.count())
        .select_from(BusinessCustomerBlock)
        .where(BusinessCustomerBlock.buyer_user_id == buyer_user_id)
    )
    return rows.scalars().all(), total.scalar_one()
