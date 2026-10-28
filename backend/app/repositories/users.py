import enum
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import Select, UnaryExpression, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased, selectinload

from app.models import AccountBlock, Business, Product, Report, User, UserRole, UserStatus
from app.repositories.catalog import LIKE_ESCAPE, like_pattern


@dataclass(frozen=True)
class AccountFilter:
    """Everything the administrator's list can be narrowed by.

    One object rather than a dozen parameters: the listing and its count must agree on what
    matches, and the surest way to keep them agreeing is to give them the same thing to read.
    """

    query: str | None = None
    roles: Sequence[UserRole] | None = None
    statuses: Sequence[UserStatus] | None = None
    registered_from: datetime | None = None
    registered_to: datetime | None = None
    last_login_from: datetime | None = None
    last_login_to: datetime | None = None
    # tri-state on purpose: None asks nothing, False asks for the accounts with none
    has_bans: bool | None = None
    has_reports: bool | None = None


class AccountSort(enum.StrEnum):
    REGISTERED = "registered"
    LAST_LOGIN = "last_login"
    EMAIL = "email"


# Newest first for the time columns, A to Z for the address: in each case the order somebody
# scanning the list would expect without being told.
_ORDER: dict[AccountSort, UnaryExpression[Any]] = {
    AccountSort.REGISTERED: User.created_at.desc(),
    AccountSort.LAST_LOGIN: User.last_login_at.desc().nulls_last(),
    AccountSort.EMAIL: User.email.asc(),
}


def _narrow[S: Select[Any]](statement: S, where: AccountFilter) -> S:
    """Shared by the listing and its count, so the two cannot disagree on what matches."""
    if where.query:
        # the login is an address or a phone, and whoever is searching knows which they have
        pattern = like_pattern(where.query)
        statement = statement.where(
            or_(
                User.email.ilike(pattern, escape=LIKE_ESCAPE),
                User.phone.ilike(pattern, escape=LIKE_ESCAPE),
            )
        )
    if where.roles is not None:
        statement = statement.where(User.role.in_(where.roles))
    if where.statuses is not None:
        statement = statement.where(User.status.in_(where.statuses))
    if where.registered_from is not None:
        statement = statement.where(User.created_at >= where.registered_from)
    if where.registered_to is not None:
        statement = statement.where(User.created_at <= where.registered_to)
    if where.last_login_from is not None:
        statement = statement.where(User.last_login_at >= where.last_login_from)
    if where.last_login_to is not None:
        statement = statement.where(User.last_login_at <= where.last_login_to)
    if where.has_bans is not None:
        statement = statement.where(_ever_banned() == where.has_bans)
    if where.has_reports is not None:
        statement = statement.where(_ever_reported() == where.has_reports)
    return statement


def _ever_banned() -> Any:
    """Ever, not now: an administrator looking for trouble wants the history, not the state."""
    return select(AccountBlock.id).where(AccountBlock.user_id == User.id).exists()


def _ever_reported() -> Any:
    """Complained about, not complaining: an administrator hunting trouble wants the subject.

    A complaint names a shop or a product, never a person, so it reaches its owner through
    what they own.
    """
    named = aliased(Business)
    selling = aliased(Business)
    return (
        select(Report.id)
        .outerjoin(named, named.id == Report.business_id)
        .outerjoin(Product, Product.id == Report.product_id)
        .outerjoin(selling, selling.id == Product.business_id)
        .where(or_(named.owner_user_id == User.id, selling.owner_user_id == User.id))
        # only the account correlates: left to itself the subquery would drag `users` into its
        # own FROM, and every account with any complaint anywhere would answer yes
        .correlate(User)
        .exists()
    )


async def get_by_id(session: AsyncSession, user_id: uuid.UUID) -> User | None:
    return await session.get(User, user_id)


async def get_by_email(session: AsyncSession, email: str) -> User | None:
    result = await session.execute(select(User).where(User.email == email))
    return result.scalar_one_or_none()


async def email_exists(session: AsyncSession, email: str) -> bool:
    result = await session.execute(select(User.id).where(User.email == email))
    return result.scalar_one_or_none() is not None


async def phone_exists(session: AsyncSession, phone: str) -> bool:
    result = await session.execute(select(User.id).where(User.phone == phone))
    return result.scalar_one_or_none() is not None


async def add(session: AsyncSession, user: User) -> User:
    session.add(user)
    await session.flush()
    return user


async def get_business_of(session: AsyncSession, user_id: uuid.UUID) -> Business | None:
    result = await session.execute(select(Business).where(Business.owner_user_id == user_id))
    return result.scalar_one_or_none()


async def get_business_with_reviews(session: AsyncSession, user_id: uuid.UUID) -> Business | None:
    """What the seller's own cabinet shows: the shop and every verdict passed on it, so a
    refusal arrives with the reason attached rather than as a bare status.

    The storefront comes along because a status change moves it too — see
    services/business_moderation._move — and a lazy load there would have nowhere to run.
    """
    result = await session.execute(
        select(Business)
        .options(selectinload(Business.reviews), selectinload(Business.store))
        .where(Business.owner_user_id == user_id)
    )
    return result.scalar_one_or_none()


async def add_business(session: AsyncSession, business: Business) -> Business:
    session.add(business)
    await session.flush()
    return business


async def search(
    session: AsyncSession,
    where: AccountFilter,
    limit: int,
    offset: int,
    sort: AccountSort = AccountSort.REGISTERED,
) -> Sequence[User]:
    """Newest first by default, so an account registered a minute ago is the one on top.

    The id breaks every tie: without it two accounts sharing a timestamp could swap places
    between pages, and the same row would be shown twice while another was never shown.
    """
    result = await session.execute(
        _narrow(select(User), where).order_by(_ORDER[sort], User.id).limit(limit).offset(offset)
    )
    return result.scalars().all()


async def count_matching(session: AsyncSession, where: AccountFilter) -> int:
    return (
        await session.execute(_narrow(select(func.count()).select_from(User), where))
    ).scalar_one()


async def get_admin(session: AsyncSession) -> User | None:
    """The administrator, whatever their status. There is at most one: a unique partial index
    on `role = 'admin'` is what makes `scalar_one_or_none` safe to say here."""
    result = await session.execute(select(User).where(User.role == UserRole.ADMIN))
    return result.scalar_one_or_none()


async def count_active_admins(session: AsyncSession) -> int:
    result = await session.execute(
        select(func.count())
        .select_from(User)
        .where(User.role == UserRole.ADMIN, User.status == UserStatus.ACTIVE)
    )
    return result.scalar_one()
