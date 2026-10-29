from typing import Annotated

from fastapi import APIRouter, Depends, File, UploadFile, status

from app.core import storage
from app.core.errors import NotFoundError
from app.deps.auth import SessionDep, SettingsDep, ensure_verified_email, require_csrf, require_role
from app.deps.business import CurrentBusiness
from app.models import User, UserRole
from app.repositories import stores as stores_repo
from app.repositories import users as users_repo
from app.schemas.store import StoreCreateRequest, StoreRead, StoreUpdateRequest
from app.services import store_branding
from app.services import stores as stores_service
from app.services.store_branding import StoreImageKind

router = APIRouter(prefix="/stores", tags=["stores"])

SellerUser = Annotated[User, Depends(require_role(UserRole.SELLER))]


async def _seller_who_answered_their_mail(user: SellerUser) -> User:
    """Opening a shop is the one thing the platform does on somebody's behalf in public, and
    an address nobody has answered at is not a way to reach the person behind it.

    Composed on top of the role rather than standing beside it, so somebody who may not open
    a shop at all is told that, and not asked to confirm an address that would not help them.
    """
    return ensure_verified_email(user)


VerifiedSeller = Annotated[User, Depends(_seller_who_answered_their_mail)]


@router.post(
    "",
    response_model=StoreRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_csrf)],
)
async def create_store(
    payload: StoreCreateRequest, user: VerifiedSeller, settings: SettingsDep, session: SessionDep
) -> StoreRead:
    business = await users_repo.get_business_of(session, user.id)
    if business is None:
        raise NotFoundError("У аккаунта нет бизнеса")
    store = await stores_service.create_store(session, settings, business, payload.subdomain)
    await session.commit()
    return StoreRead.of(store, business)


@router.get("/me", response_model=StoreRead)
async def read_my_store(user: SellerUser, session: SessionDep) -> StoreRead:
    business = await users_repo.get_business_of(session, user.id)
    store = None if business is None else await stores_repo.get_by_business(session, business.id)
    if store is None or business is None:
        raise NotFoundError("У аккаунта нет витрины")
    return StoreRead.of(store, business)


@router.patch("/me", response_model=StoreRead, dependencies=[Depends(require_csrf)])
async def update_my_store(
    payload: StoreUpdateRequest, business: CurrentBusiness, session: SessionDep
) -> StoreRead:
    store = await store_branding.update_store(session, business, payload)
    await session.commit()
    return StoreRead.of(store, business)


# the literal segment keeps this off /stores/me/contacts, which an enum path would swallow
@router.put("/me/images/{kind}", response_model=StoreRead, dependencies=[Depends(require_csrf)])
async def set_store_image(
    kind: StoreImageKind,
    business: CurrentBusiness,
    settings: SettingsDep,
    session: SessionDep,
    file: Annotated[UploadFile, File()],
) -> StoreRead:
    """PUT rather than POST: a storefront has one logo and one banner, so a second upload
    replaces the first instead of adding to a gallery."""
    store, displaced = await store_branding.set_image(session, settings, business.id, kind, file)
    await session.commit()
    # only after the new address is committed: the reverse order would leave the page
    # pointing at an object that is already gone
    if displaced is not None:
        await storage.delete_object(settings, displaced)
    return StoreRead.of(store, business)


@router.delete("/me/images/{kind}", response_model=StoreRead, dependencies=[Depends(require_csrf)])
async def clear_store_image(
    kind: StoreImageKind,
    business: CurrentBusiness,
    settings: SettingsDep,
    session: SessionDep,
) -> StoreRead:
    store, displaced = await store_branding.clear_image(session, settings, business.id, kind)
    await session.commit()
    if displaced is not None:
        await storage.delete_object(settings, displaced)
    return StoreRead.of(store, business)
