from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.core.errors import NotFoundError
from app.deps.auth import SessionDep, SignedInUser, require_csrf, require_role
from app.models import User, UserRole
from app.repositories import users as users_repo
from app.schemas.auth import BusinessOnboardingRequest, BusinessRead, UserRead
from app.services import business_moderation, businesses

router = APIRouter(tags=["users"])

SellerUser = Annotated[User, Depends(require_role(UserRole.SELLER))]


@router.get("/users/me", response_model=UserRead)
async def read_me(user: SignedInUser) -> UserRead:
    """Reachable while a password is still owed: this is how the client finds out it owes one."""
    return UserRead.model_validate(user)


@router.get("/users/me/business", response_model=BusinessRead)
async def read_my_business(user: SellerUser, session: SessionDep) -> BusinessRead:
    """With the verdicts attached: a refusal the seller cannot read is one they cannot answer."""
    business = await users_repo.get_business_with_reviews(session, user.id)
    if business is None:
        raise NotFoundError("У аккаунта нет магазина")
    return BusinessRead.of(business)


@router.post(
    "/users/me/business",
    response_model=BusinessRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_csrf)],
)
async def open_my_business(
    user: SellerUser, payload: BusinessOnboardingRequest, session: SessionDep
) -> BusinessRead:
    """For the seller who arrived through Google and therefore has no business yet.

    A password registration creates both at once and never reaches this; the route exists
    because the other way in cannot. It is deliberately not restricted to Google accounts —
    what matters is whether a business exists, and the unique index answers that better than
    a check on how somebody signed up.
    """
    business = await businesses.open_for(session, user, payload)
    await session.commit()
    await session.refresh(business, attribute_names=["reviews", "created_at"])
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
