"""What the machine and the services are doing right now.

Current state only — no history, no stored series, no background collector (decision of
2026-10-28). Everything here is read at the moment it is asked for, which is also why it is
cheap enough to refresh every ten seconds and why nothing has to be cleaned up later.

One caveat worth knowing before trusting a number: inside a container `psutil` reports the
host's processor and memory, not the container's, and the disk figure is whatever is mounted
at the path asked about. On the stand that is the same machine and the numbers agree with
`docker stats`, `df` and `free`; under a quota they would not.
"""

import time
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

import psutil
from sqlalchemy import Select, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from app.models import (
    Business,
    BusinessStatus,
    Product,
    RefreshToken,
    Report,
    ReportStatus,
    User,
    UserRole,
)


@dataclass(frozen=True)
class Resources:
    cpu_percent: float
    memory_percent: float
    memory_total_mb: int
    memory_used_mb: int
    disk_percent: float
    disk_total_gb: int
    disk_free_gb: int
    uptime_seconds: int


@dataclass(frozen=True)
class Occupancy:
    """What the platform is holding, counted the only way that cannot drift: by asking."""

    users: int
    sellers: int
    products: int
    businesses_pending: int
    reports_open: int
    live_sessions: int
    database_size_mb: int


_MB = 1024 * 1024
_GB = _MB * 1024


def resources() -> Resources:
    memory = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    return Resources(
        # a zero interval compares against the previous call rather than blocking for a
        # sample: the page refreshes often enough that the previous call is seconds ago
        cpu_percent=psutil.cpu_percent(interval=0.0),
        memory_percent=memory.percent,
        memory_total_mb=memory.total // _MB,
        memory_used_mb=(memory.total - memory.available) // _MB,
        disk_percent=disk.percent,
        disk_total_gb=disk.total // _GB,
        disk_free_gb=disk.free // _GB,
        uptime_seconds=int(time.time() - psutil.boot_time()),
    )


async def occupancy(session: AsyncSession) -> Occupancy:
    return Occupancy(
        users=await _count(session, select(func.count()).select_from(User)),
        sellers=await _count(
            session, select(func.count()).select_from(User).where(User.role == UserRole.SELLER)
        ),
        products=await _count(
            session, select(func.count()).select_from(Product).where(Product.archived_at.is_(None))
        ),
        businesses_pending=await _count(
            session,
            select(func.count())
            .select_from(Business)
            .where(Business.status == BusinessStatus.PENDING),
        ),
        reports_open=await _count(
            session,
            select(func.count()).select_from(Report).where(Report.status == ReportStatus.OPEN),
        ),
        live_sessions=await _count(
            session,
            select(func.count())
            .select_from(RefreshToken)
            .where(
                RefreshToken.revoked_at.is_(None),
                RefreshToken.expires_at > datetime.now(UTC),
            ),
        ),
        database_size_mb=await _database_size_mb(session),
    )


@dataclass(frozen=True)
class DayOfActivity:
    day: date
    registrations: int
    logins: int
    products: int
    reports: int


async def activity(session: AsyncSession, days: int) -> list[DayOfActivity]:
    """The last N days, oldest first, with quiet days present and zeroed.

    A series with holes in it reads as a series that was not collected; one that says zero
    reads as a day when nothing happened, which is the thing actually being reported.
    """
    since = datetime.now(UTC) - timedelta(days=days - 1)
    first = since.date()
    registrations = await _per_day(session, User.created_at, since)
    logins = await _per_day(session, User.last_login_at, since)
    products = await _per_day(session, Product.created_at, since)
    reports = await _per_day(session, Report.created_at, since)
    return [
        DayOfActivity(
            day=first + timedelta(days=offset),
            registrations=registrations.get(first + timedelta(days=offset), 0),
            logins=logins.get(first + timedelta(days=offset), 0),
            products=products.get(first + timedelta(days=offset), 0),
            reports=reports.get(first + timedelta(days=offset), 0),
        )
        for offset in range(days)
    ]


async def _per_day(
    session: AsyncSession, column: InstrumentedAttribute[datetime | None], since: datetime
) -> dict[date, int]:
    """One grouped query per series. `last_login_at` is nullable, and a NULL groups to
    nothing rather than to a day — which is right: an account that never came back has no
    day to count on."""
    day = func.date(column)
    result = await session.execute(
        select(day, func.count()).where(column >= since).group_by(day).order_by(day)
    )
    return {row[0]: int(row[1]) for row in result.all()}


async def _count(session: AsyncSession, statement: Select[tuple[int]]) -> int:
    return int((await session.execute(statement)).scalar_one())


async def _database_size_mb(session: AsyncSession) -> int:
    result = await session.execute(text("SELECT pg_database_size(current_database())"))
    return int(result.scalar_one()) // _MB
