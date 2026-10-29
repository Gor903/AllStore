import uuid
from collections.abc import Sequence
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog, User
from app.repositories import audit
from app.repositories.audit import JournalFilter


async def record(
    session: AsyncSession,
    actor: User | None,
    action: str,
    entity_type: str,
    entity_id: uuid.UUID,
    **details: Any,
) -> AuditLog:
    """Writes one entry. Called from inside the service that performs the action, in the
    same transaction: an action that lands without its record, or a record without its
    action, would make the journal something one has to double-check rather than trust.

    The actor may be nobody. Almost every entry here is somebody doing something, but not
    all: a token replayed after it was retired was presented by a party the platform cannot
    name, and writing the account's owner in that column would say they did it. The column
    has always been nullable — an actor can be deleted — and the reading side already shows
    an entry without one."""
    return await audit.add(
        session,
        AuditLog(
            actor_user_id=None if actor is None else actor.id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            details=details,
        ),
    )


async def list_entries(
    session: AsyncSession, where: JournalFilter, limit: int, offset: int
) -> tuple[Sequence[AuditLog], int]:
    return (
        await audit.list_entries(session, where, limit, offset),
        await audit.count_entries(session, where),
    )
