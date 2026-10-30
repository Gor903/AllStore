"""Opening a business for a seller who has an account and nothing to sell from.

Registering on the public form asks for everything at once, so it never needs this. The one
path that can leave a seller without a business is `scripts.grant_role`, which knows an
address and a role and nothing a shop needs: a legal name and a name to trade under, both
NOT NULL on the table. This is the way out of that state.
"""

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError
from app.models import Business, User
from app.repositories import users as users_repo
from app.schemas.auth import BusinessOnboardingRequest


class AlreadyHasOne(ConflictError):
    """One seller, one business — the MVP says so and the unique index enforces it."""

    code = "business_exists"


async def open_for(
    session: AsyncSession, user: User, details: BusinessOnboardingRequest
) -> Business:
    """Creates the business, pending moderation like any other.

    The unique index on `owner_user_id` is what decides, not a look beforehand: looking and
    then inserting is two statements with a gap between them, and two taps on a slow
    connection both pass the look. A savepoint, because a failed insert would otherwise
    poison the transaction the phone is written in.
    """
    if details.phone is not None and user.phone is None:
        # Nobody asked them for it on the way in, and a shop that cannot be telephoned is a
        # shop a moderator cannot check. An existing number is left alone: changing it is a
        # different act, with a different screen.
        user.phone = details.phone
    try:
        async with session.begin_nested():
            return await users_repo.add_business(
                session,
                Business(
                    owner_user_id=user.id,
                    legal_name=details.legal_name,
                    display_name=details.display_name,
                ),
            )
    except IntegrityError as taken:
        raise AlreadyHasOne("У этого аккаунта уже есть магазин") from taken
