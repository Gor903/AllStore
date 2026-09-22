from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.errors import NotFoundError
from app.deps.auth import CurrentUser, SessionDep, require_role
from app.models import User, UserRole
from app.repositories import users as users_repo
from app.schemas.auth import BusinessRead, UserRead

router = APIRouter(tags=["users"])

SellerUser = Annotated[User, Depends(require_role(UserRole.SELLER))]


@router.get("/users/me", response_model=UserRead)
async def read_me(user: CurrentUser) -> UserRead:
    return UserRead.model_validate(user)


@router.get("/users/me/business", response_model=BusinessRead)
async def read_my_business(user: SellerUser, session: SessionDep) -> BusinessRead:
    business = await users_repo.get_business_of(session, user.id)
    if business is None:
        raise NotFoundError("У аккаунта нет магазина")
    return BusinessRead.model_validate(business)
