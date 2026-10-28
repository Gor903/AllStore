"""What has passed between the people on this platform.

One route group rather than one per panel, for the same reason barring is one: who sees what
is settled by rank inside the service, not by which URL was called. Two endpoints under two
prefixes would be two places for that rule to drift apart.
"""

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.deps.auth import SessionDep, require_role
from app.models import User, UserRole
from app.schemas.admin import IncidentListResponse
from app.services import incidents
from app.services.incidents import IncidentFilter, IncidentKind

router = APIRouter(prefix="/incidents", tags=["incidents"])

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100

StaffUser = Annotated[User, Depends(require_role(UserRole.MODERATOR, UserRole.ADMIN))]
Limit = Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)]
Offset = Annotated[int, Query(ge=0)]


@router.get("", response_model=IncidentListResponse)
async def list_incidents(
    actor: StaffUser,
    session: SessionDep,
    user_id: uuid.UUID | None = None,
    kind: IncidentKind | None = None,
    since: Annotated[datetime | None, Query()] = None,
    until: Annotated[datetime | None, Query()] = None,
    limit: Limit = DEFAULT_PAGE_SIZE,
    offset: Offset = 0,
) -> IncidentListResponse:
    """Complaints and shop-level bans, newest first, narrowed to one person if asked.

    A moderator's feed holds only what passed between buyers and sellers: an event with
    another moderator or the administrator on either side does not exist for them.
    """
    where = IncidentFilter(user_id=user_id, kind=kind, since=since, until=until)
    items, total = await incidents.between(session, actor, where, limit, offset)
    return IncidentListResponse.of(items, total, limit, offset)
