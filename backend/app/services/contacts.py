import uuid
from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ValidationFailedError
from app.models import Business, SocialLink
from app.repositories import contacts
from app.schemas.contact import ContactsRequest


class ContactsRequiredError(ValidationFailedError):
    code = "contacts_required"


async def list_contacts(session: AsyncSession, business_id: uuid.UUID) -> Sequence[SocialLink]:
    return await contacts.list_for_business(session, business_id)


async def replace_contacts(
    session: AsyncSession, business: Business, payload: ContactsRequest
) -> Sequence[SocialLink]:
    links = [
        SocialLink(business_id=business.id, platform=item.platform, value=item.value)
        for item in payload.items
    ]
    return await contacts.replace(session, business.id, links)


async def require_contact(session: AsyncSession, business_id: uuid.UUID) -> None:
    """A product with no way to reach its seller is a dead end: the MVP has no cart and no
    checkout, so the contact is the whole of the transaction (раздел 15 продуктового плана).

    The check guards the two doors into the moderation queue, not the moderator's verdict:
    the seller is the one who can fix it, and they find out before a moderator spends time.
    Products published before this rule existed keep their place — see the journal entry.
    """
    if await contacts.count_for_business(session, business_id) == 0:
        raise ContactsRequiredError(
            "Добавьте способ связи в настройках магазина — без него покупателю некуда обратиться"
        )
