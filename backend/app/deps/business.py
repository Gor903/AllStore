from typing import Annotated

from fastapi import Depends

from app.core.errors import NotFoundError
from app.deps.auth import SessionDep, require_role
from app.models import Business, User, UserRole
from app.repositories import users as users_repo

SellerUser = Annotated[User, Depends(require_role(UserRole.SELLER))]


async def get_current_business(user: SellerUser, session: SessionDep) -> Business:
    """The tenant of a dashboard request, resolved from the session and never from the Host.

    Every seller-facing query filters on the business this returns, so a forged Host header
    or a guessed identifier in the path cannot reach another seller's data.
    """
    business = await users_repo.get_business_of(session, user.id)
    if business is None:
        raise NotFoundError("У аккаунта нет бизнеса")
    return business


CurrentBusiness = Annotated[Business, Depends(get_current_business)]
