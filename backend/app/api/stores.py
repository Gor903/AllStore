from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.core.errors import NotFoundError
from app.deps.auth import SessionDep, SettingsDep, require_csrf, require_role
from app.models import User, UserRole
from app.repositories import stores as stores_repo
from app.repositories import users as users_repo
from app.schemas.store import StoreCreateRequest, StoreRead
from app.services import stores as stores_service

router = APIRouter(prefix="/stores", tags=["stores"])

SellerUser = Annotated[User, Depends(require_role(UserRole.SELLER))]


@router.post(
    "",
    response_model=StoreRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_csrf)],
)
async def create_store(
    payload: StoreCreateRequest, user: SellerUser, settings: SettingsDep, session: SessionDep
) -> StoreRead:
    business = await users_repo.get_business_of(session, user.id)
    if business is None:
        raise NotFoundError("У аккаунта нет бизнеса")
    store = await stores_service.create_store(session, settings, business, payload.subdomain)
    await session.commit()
    return StoreRead.model_validate(store)


@router.get("/me", response_model=StoreRead)
async def read_my_store(user: SellerUser, session: SessionDep) -> StoreRead:
    business = await users_repo.get_business_of(session, user.id)
    store = None if business is None else await stores_repo.get_by_business(session, business.id)
    if store is None:
        raise NotFoundError("У аккаунта нет витрины")
    return StoreRead.model_validate(store)
