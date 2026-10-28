"""Who may act on whom. One table, consulted by every service that touches an account.

The four roles are not peers. A moderator judges buyers and sellers, an administrator judges
moderators, and nobody judges the administrator: there is exactly one, and an account another
account could take away would not be the last resort it exists to be.

Everything follows from the ranks below and one rule — an actor reaches strictly lower ranks
only. Self-blocking, a moderator barring a moderator and an administrator barring themselves
all fall out of it without a special case, which is why the rule is a rank and not a list of
exceptions.
"""

import enum

from app.core.errors import PermissionDeniedError
from app.models import User, UserRole

# buyer and seller share a rank: neither has any authority over accounts, and a seller's extra
# rights are over their own shop rather than over people
RANK: dict[UserRole, int] = {
    UserRole.BUYER: 0,
    UserRole.SELLER: 0,
    UserRole.MODERATOR: 1,
    UserRole.ADMIN: 2,
}


class NotAllowedError(PermissionDeniedError):
    code = "not_allowed"


def outranks(actor: UserRole, target: UserRole) -> bool:
    return RANK[actor] > RANK[target]


def may_block(actor: UserRole, target: UserRole) -> bool:
    """Blocking an account is an act of authority, so it needs a rank above the target's."""
    return outranks(actor, target)


def may_change_role(actor: UserRole, target: UserRole) -> bool:
    """Appointing is the administrator's alone: a moderator who could appoint moderators
    would be an administrator under another name."""
    return actor is UserRole.ADMIN and outranks(actor, target)


def may_invite_moderator(actor: UserRole) -> bool:
    return actor is UserRole.ADMIN


def may_read_audit_log(actor: UserRole) -> bool:
    """The journal names who did what, including what moderators did — not a moderator's."""
    return actor is UserRole.ADMIN


class Scope(enum.StrEnum):
    """Which screen is asking. Not a right — a subject."""

    # the people who use the platform
    ACCOUNTS = "accounts"
    # the people who run it
    STAFF = "staff"


def reachable_roles(actor: UserRole) -> list[UserRole]:
    """Every role this actor may act on, whatever screen they are on.

    This answers "may I", not "show me". The two were one function once, and merging them
    meant the administrator's list of ordinary accounts had moderators in it — the right
    answer to the wrong question.
    """
    return [role for role in UserRole if outranks(actor, role)]


def listable_roles(actor: UserRole, scope: Scope) -> list[UserRole]:
    """What one screen shows, which is narrower than what the actor may do.

    An administrator may bar a moderator, and does it in the panel that is about moderators.
    Mixing them into the list of buyers and sellers would make that list mean two things, and
    the one place that is about people who run the platform would not be the only one.
    """
    if scope is Scope.STAFF:
        return [UserRole.MODERATOR] if actor is UserRole.ADMIN else []
    return [role for role in (UserRole.BUYER, UserRole.SELLER) if outranks(actor, role)]


def ensure_may_block(actor: User, target: User) -> None:
    if actor.id == target.id:
        # the rank rule already refuses it; the message is what differs, because locking
        # yourself out by accident is a different mistake from overreaching
        raise NotAllowedError("Себя заблокировать нельзя")
    if not may_block(actor.role, target.role):
        raise NotAllowedError(_refusal(actor.role, target.role))


def ensure_may_change_role(actor: User, target: User) -> None:
    if actor.id == target.id:
        raise NotAllowedError("Свою роль менять нельзя")
    if not may_change_role(actor.role, target.role):
        raise NotAllowedError(_refusal(actor.role, target.role))


def _refusal(actor: UserRole, target: UserRole) -> str:
    if RANK[actor] == RANK[target]:
        return "Это аккаунт того же уровня — такие решения принимает роль выше"
    return "Недостаточно прав: этот аккаунт выше вас"
