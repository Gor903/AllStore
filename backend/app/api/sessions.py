"""The devices an account is signed in on, and taking one of them away.

Everything here is scoped to the person asking. There is no administrative view of somebody
else's devices and there should not be: barring an account already ends every session it has
(`services/account_blocks.py`), and an administrator who could read the list would be reading
where a person has been, which is not a thing the platform needs anybody to be able to do.
"""

import uuid

from fastapi import APIRouter, Depends, Response, status

from app.core.cookies import clear_session_cookies
from app.core.errors import NotFoundError
from app.deps.auth import CurrentSession, CurrentUser, SessionDep, SettingsDep, require_bound_csrf
from app.repositories import sessions as repo
from app.schemas.session import DeviceKeyRequest, SessionListResponse, SessionRead
from app.services import device_keys
from app.services import sessions as session_service

router = APIRouter(prefix="/auth/sessions", tags=["sessions"])


class SessionNotFoundError(NotFoundError):
    code = "session_not_found"


@router.get("", response_model=SessionListResponse)
async def list_sessions(
    user: CurrentUser, current: CurrentSession, session: SessionDep
) -> SessionListResponse:
    rows = await repo.live_for_user(session, user.id)
    return SessionListResponse(
        items=[SessionRead.of(row, current=row.family_id == current.family_id) for row in rows]
    )


@router.delete(
    "/{family_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_bound_csrf)],
)
async def revoke_session(
    family_id: uuid.UUID,
    user: CurrentUser,
    current: CurrentSession,
    response: Response,
    settings: SettingsDep,
    session: SessionDep,
) -> None:
    """Signs one device out. Naming the one you are holding is allowed — it is just a logout
    with a longer way of saying it, so the cookies go too."""
    rows = await repo.live_for_user(session, user.id)
    if not any(row.family_id == family_id for row in rows):
        raise SessionNotFoundError("Такого устройства нет")
    await repo.revoke_family(session, family_id, session_service.SIGNED_OUT)
    await session.commit()
    if family_id == current.family_id:
        clear_session_cookies(response, settings)


@router.delete(
    "",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_bound_csrf)],
)
async def revoke_other_sessions(
    user: CurrentUser, current: CurrentSession, session: SessionDep
) -> None:
    """ "Sign out everywhere else" — the one answer to "somebody else is in my account" that
    does not require knowing which of the devices on the list is theirs."""
    await repo.revoke_every_other_family(
        session, user.id, current.family_id, session_service.SIGNED_OUT_ELSEWHERE
    )
    await session.commit()


@router.post(
    "/device-key",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_bound_csrf)],
)
async def bind_device_key(
    payload: DeviceKeyRequest,
    _: CurrentUser,
    current: CurrentSession,
    session: SessionDep,
    settings: SettingsDep,
) -> None:
    """Attaches this browser's key to this session, and buys it a longer life for it.

    A session that can prove it is still the same device is worth trusting for longer than one
    that can only produce a cookie, so binding extends the absolute clock rather than the
    unbound case being punished for a browser's shortcomings.
    """
    if await device_keys.bind(session, current, payload.public_key):
        await session_service.extend_for_a_bound_device(session, settings, current)
    await session.commit()
