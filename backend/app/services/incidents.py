"""What has passed between the people on this platform, as far as the database knows.

Not the activity feed the plan originally described: there are no orders, no reviews and no
messages here, so a feed of those would be a feed of nothing. What does exist is the record
of things going wrong between a buyer and a seller — a complaint, a shop closing its door to
somebody, a verdict on a shop — and that is what this reads.

When orders and messages arrive they become further sources for the same endpoint rather than
a reason to rewrite it.

Who sees what follows the ranks, as everywhere else. A moderator sees incidents between the
people the platform serves; events involving another moderator or the administrator do not
exist for them, because a feed is exactly the side door the listings were closed against.
"""

import enum
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.models import (
    Business,
    BusinessCustomerBlock,
    Report,
    User,
    UserRole,
)
from app.services import permissions


class IncidentKind(enum.StrEnum):
    REPORT = "report"
    CUSTOMER_BLOCK = "customer_block"


@dataclass(frozen=True)
class Incident:
    kind: IncidentKind
    happened_at: datetime
    # the two people it passed between; either may be absent when the account is gone
    initiator_email: str | None
    counterpart_email: str | None
    subject: str
    reason: str | None


@dataclass(frozen=True)
class IncidentFilter:
    user_id: uuid.UUID | None = None
    kind: IncidentKind | None = None
    since: datetime | None = None
    until: datetime | None = None


async def between(
    session: AsyncSession, actor: User, where: IncidentFilter, limit: int, offset: int
) -> tuple[Sequence[Incident], int]:
    """Newest first. Collected in Python rather than as one union query: two small ordered
    reads merge cheaply at these sizes, and the alternative is a union whose every future
    source has to match its column list exactly."""
    visible = _visible_to(actor)
    reports = await _reports(session, where, visible)
    blocks = await _customer_blocks(session, where, visible)
    everything = sorted(reports + blocks, key=lambda item: item.happened_at, reverse=True)
    return everything[offset : offset + limit], len(everything)


def _visible_to(actor: User) -> Sequence[UserRole]:
    """Whose events this actor may see — a different question from whose accounts they list.

    The administrator sees everything, moderators included: watching what the staff does is
    the whole point of their panel. A moderator sees only what passed between the people the
    platform serves.
    """
    if actor.role is UserRole.ADMIN:
        return list(UserRole)
    return permissions.listable_roles(actor.role, permissions.Scope.ACCOUNTS)


async def _reports(
    session: AsyncSession, where: IncidentFilter, visible: Sequence[UserRole]
) -> list[Incident]:
    if where.kind is IncidentKind.CUSTOMER_BLOCK:
        return []
    reporter = aliased(User)
    owner = aliased(User)
    statement = (
        select(Report, reporter, owner, Business)
        .outerjoin(reporter, reporter.id == Report.reporter_user_id)
        .outerjoin(Business, Business.id == Report.business_id)
        .outerjoin(owner, owner.id == Business.owner_user_id)
    )
    if where.since is not None:
        statement = statement.where(Report.created_at >= where.since)
    if where.until is not None:
        statement = statement.where(Report.created_at <= where.until)
    if where.user_id is not None:
        statement = statement.where((reporter.id == where.user_id) | (owner.id == where.user_id))
    rows = (await session.execute(statement)).all()
    return [
        Incident(
            kind=IncidentKind.REPORT,
            happened_at=report.created_at,
            initiator_email=None if person is None else person.email,
            counterpart_email=None if shopkeeper is None else shopkeeper.email,
            subject="магазин" if report.product_id is None else "товар",
            reason=report.reason,
        )
        for report, person, shopkeeper, _ in rows
        if _both_visible(person, shopkeeper, visible)
    ]


async def _customer_blocks(
    session: AsyncSession, where: IncidentFilter, visible: Sequence[UserRole]
) -> list[Incident]:
    if where.kind is IncidentKind.REPORT:
        return []
    buyer = aliased(User)
    owner = aliased(User)
    statement = (
        select(BusinessCustomerBlock, buyer, owner)
        .join(buyer, buyer.id == BusinessCustomerBlock.buyer_user_id)
        .join(Business, Business.id == BusinessCustomerBlock.business_id)
        .outerjoin(owner, owner.id == Business.owner_user_id)
    )
    if where.since is not None:
        statement = statement.where(BusinessCustomerBlock.created_at >= where.since)
    if where.until is not None:
        statement = statement.where(BusinessCustomerBlock.created_at <= where.until)
    if where.user_id is not None:
        statement = statement.where((buyer.id == where.user_id) | (owner.id == where.user_id))
    rows = (await session.execute(statement)).all()
    return [
        Incident(
            kind=IncidentKind.CUSTOMER_BLOCK,
            happened_at=block.created_at,
            initiator_email=None if shopkeeper is None else shopkeeper.email,
            counterpart_email=customer.email,
            subject="магазин закрыт покупателю",
            reason=block.reason,
        )
        for block, customer, shopkeeper in rows
        if _both_visible(customer, shopkeeper, visible)
    ]


def _both_visible(one: User | None, other: User | None, visible: Sequence[UserRole]) -> bool:
    """An incident with staff on either side does not exist for somebody who may not see them.

    Checked on both parties rather than on the subject: a complaint filed *by* a moderator
    names them just as surely as one filed about them.
    """
    return all(person is None or person.role in visible for person in (one, other))
