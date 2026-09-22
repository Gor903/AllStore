from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.errors import NotFoundError
from app.deps.auth import SessionDep, require_csrf, require_role
from app.models import User, UserRole
from app.repositories import users as users_repo
from app.schemas.contact import ContactsRequest, ContactsResponse
from app.services import contacts as contacts_service

# contacts hang off the business, but the seller thinks of them as their shop's — so they
# live under the shop, next to the rest of what the settings screen edits
router = APIRouter(prefix="/stores/me/contacts", tags=["contacts"])

SellerUser = Annotated[User, Depends(require_role(UserRole.SELLER))]


@router.get("", response_model=ContactsResponse)
async def read_my_contacts(user: SellerUser, session: SessionDep) -> ContactsResponse:
    business = await users_repo.get_business_of(session, user.id)
    if business is None:
        raise NotFoundError("У аккаунта нет бизнеса")
    return ContactsResponse.of(list(await contacts_service.list_contacts(session, business.id)))


@router.put("", response_model=ContactsResponse, dependencies=[Depends(require_csrf)])
async def replace_my_contacts(
    payload: ContactsRequest, user: SellerUser, session: SessionDep
) -> ContactsResponse:
    business = await users_repo.get_business_of(session, user.id)
    if business is None:
        raise NotFoundError("У аккаунта нет бизнеса")
    links = await contacts_service.replace_contacts(session, business, payload)
    await session.commit()
    return ContactsResponse.of(list(links))
