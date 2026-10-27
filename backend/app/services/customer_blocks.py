"""A seller deciding who is welcome in their own shop.

Narrow on purpose. A seller may close their door to one buyer; they have no say over whether
that person uses the rest of the platform, so nothing here touches `users.status` and nothing
here is reachable from the global ban. The buyer goes on browsing every other shop, and goes
on being able to complain about this one — a complaint is addressed to moderators, not to the
shop, and barring somebody from your shop must not bar them from reporting it.

Who the shop disappears for is decided in the catalogue filter rather than route by route
(see `repositories/catalog.visible_to`), so one rule covers the listing, the search, the
storefront and a link saved last week.

An administrator may lift such a block. Moderators may read them: a shop that has barred
half its customers is something the queue should be able to see.
"""

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, NotFoundError, PermissionDeniedError
from app.models import Business, BusinessCustomerBlock, User, UserRole
from app.repositories import customer_blocks as blocks_repo
from app.repositories import users as users_repo
from app.services import audit

ENTITY = "customer_block"


class BuyerNotFoundError(NotFoundError):
    code = "buyer_not_found"


class NotABuyerError(ConflictError):
    code = "not_a_buyer"


class AlreadyBlockedError(ConflictError):
    code = "already_blocked"


class BlockNotFoundError(NotFoundError):
    code = "block_not_found"


class NotYourBlockError(PermissionDeniedError):
    code = "not_your_block"


class StoreAccessBlockedError(PermissionDeniedError):
    """What a barred buyer is told when they open the shop directly.

    Not a 404. They know the shop exists — they were shopping there — so pretending it
    vanished would be a riddle rather than a protection. The listing stays silent because a
    list has nowhere to say it; a direct visit gets a straight answer.
    """

    code = "store_access_blocked"


async def block(
    session: AsyncSession, business: Business, seller: User, email: str, reason: str
) -> BusinessCustomerBlock:
    """By address, because that is how a seller knows the person they fell out with.

    It does reveal whether an address has an account here. The disclosure is narrow and
    deliberate: the asker is a signed-in, named seller and the attempt is journalled, which
    is a different proposition from an anonymous form answering the same question.
    """
    buyer = await users_repo.get_by_email(session, email.strip().lower())
    if buyer is None:
        raise BuyerNotFoundError("Покупатель с таким адресом не найден")
    if buyer.role is not UserRole.BUYER:
        raise NotABuyerError("Так можно закрыть магазин только покупателю")
    if await blocks_repo.get_in_force(session, business.id, buyer.id) is not None:
        raise AlreadyBlockedError("Этому покупателю магазин уже закрыт")

    created = await blocks_repo.add(
        session,
        BusinessCustomerBlock(
            business_id=business.id,
            buyer_user_id=buyer.id,
            reason=reason,
            created_by_user_id=seller.id,
        ),
    )
    await audit.record(
        session, seller, "store.customer_blocked", ENTITY, created.id, buyer=buyer.email
    )
    return created


async def revoke(
    session: AsyncSession, actor: User, block_id: uuid.UUID, business: Business | None
) -> BusinessCustomerBlock:
    """Lifted by the shop that imposed it, or by an administrator over its head."""
    found = await blocks_repo.get(session, block_id)
    if found is None:
        raise BlockNotFoundError("Ограничение не найдено")
    if business is not None and found.business_id != business.id:
        # a seller may only undo their own door; 403 rather than 404 is safe here because
        # the identifier came from their own screen or from nowhere
        raise NotYourBlockError("Это ограничение другого магазина")
    if not found.in_force:
        raise BlockNotFoundError("Ограничение уже снято")

    found.revoked_at = datetime.now(UTC)
    found.revoked_by_user_id = actor.id
    await session.flush()
    await audit.record(session, actor, "store.customer_unblocked", ENTITY, found.id)
    return found


async def ensure_may_see(
    session: AsyncSession, business_id: uuid.UUID, viewer_id: uuid.UUID | None
) -> None:
    if await blocks_repo.is_blocked(session, business_id, viewer_id):
        raise StoreAccessBlockedError("Магазин ограничил вам доступ")


async def list_for_business(
    session: AsyncSession, business_id: uuid.UUID, limit: int, offset: int
) -> tuple[Sequence[BusinessCustomerBlock], int]:
    return await blocks_repo.list_for_business(session, business_id, limit, offset)


async def list_for_buyer(
    session: AsyncSession, buyer_user_id: uuid.UUID, limit: int, offset: int
) -> tuple[Sequence[BusinessCustomerBlock], int]:
    return await blocks_repo.list_for_buyer(session, buyer_user_id, limit, offset)
