import uuid

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import TotpCredential, TotpRecoveryCode


async def credential_of(session: AsyncSession, user_id: uuid.UUID) -> TotpCredential | None:
    """Whatever this account has, confirmed or half-enrolled."""
    result = await session.execute(select(TotpCredential).where(TotpCredential.user_id == user_id))
    return result.scalar_one_or_none()


async def is_in_force(session: AsyncSession, user_id: uuid.UUID) -> bool:
    """Asked on every authorized request a staff account makes, so it reads one indexed row
    and no more — an unfinished enrolment is not a second factor and does not count."""
    result = await session.execute(
        select(TotpCredential.id).where(
            TotpCredential.user_id == user_id, TotpCredential.confirmed_at.is_not(None)
        )
    )
    return result.scalar_one_or_none() is not None


async def put(session: AsyncSession, credential: TotpCredential) -> TotpCredential:
    session.add(credential)
    await session.flush()
    return credential


async def forget(session: AsyncSession, user_id: uuid.UUID) -> None:
    """Everything about this account's second factor, the unused recovery codes included.

    Spent codes go too. They are kept only to stop a code being spent twice, and a code
    belonging to a secret that no longer exists cannot be spent at all.
    """
    await session.execute(delete(TotpCredential).where(TotpCredential.user_id == user_id))
    await session.execute(delete(TotpRecoveryCode).where(TotpRecoveryCode.user_id == user_id))
    await session.flush()


async def add_recovery_codes(session: AsyncSession, codes: list[TotpRecoveryCode]) -> None:
    session.add_all(codes)
    await session.flush()


async def unused_recovery_code(
    session: AsyncSession, user_id: uuid.UUID, code_hash: str
) -> TotpRecoveryCode | None:
    result = await session.execute(
        select(TotpRecoveryCode).where(
            TotpRecoveryCode.user_id == user_id,
            TotpRecoveryCode.code_hash == code_hash,
            TotpRecoveryCode.used_at.is_(None),
        )
    )
    return result.scalar_one_or_none()


async def recovery_codes_left(session: AsyncSession, user_id: uuid.UUID) -> int:
    """What the settings screen shows: a count nobody can turn back into a code."""
    result = await session.execute(
        select(func.count())
        .select_from(TotpRecoveryCode)
        .where(TotpRecoveryCode.user_id == user_id, TotpRecoveryCode.used_at.is_(None))
    )
    return int(result.scalar_one())
