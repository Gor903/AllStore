from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.errors import NotFoundError
from app.deps.auth import CurrentUser, SessionDep, require_csrf, require_role
from app.models import User, UserRole
from app.repositories import users as users_repo
from app.schemas.auth import BusinessRead, UserRead
from app.services import business_moderation

router = APIRouter(tags=["users"])

SellerUser = Annotated[User, Depends(require_role(UserRole.SELLER))]


@router.get("/users/me", response_model=UserRead)
async def read_me(user: CurrentUser) -> UserRead:
    return UserRead.model_validate(user)


@router.get("/users/me/business", response_model=BusinessRead)
async def read_my_business(user: SellerUser, session: SessionDep) -> BusinessRead:
    """With the verdicts attached: a refusal the seller cannot read is one they cannot answer."""
    business = await users_repo.get_business_with_reviews(session, user.id)
    if business is None:
        raise NotFoundError("У аккаунта нет магазина")
    return BusinessRead.of(business)


@router.post(
    "/users/me/business/resubmit",
    response_model=BusinessRead,
    dependencies=[Depends(require_csrf)],
)
async def resubmit_my_business(user: SellerUser, session: SessionDep) -> BusinessRead:
    """The applicant answering a refusal: back into the queue, with the history intact."""
    business = await users_repo.get_business_with_reviews(session, user.id)
    if business is None:
        raise NotFoundError("У аккаунта нет магазина")
    await business_moderation.resubmit(session, user, business)
    await session.commit()
    await session.refresh(business, attribute_names=["reviews", "updated_at"])
    return BusinessRead.of(business)
