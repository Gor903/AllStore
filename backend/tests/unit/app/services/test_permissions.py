"""The access matrix of раздел 6 of the refactor plan, asserted role by role.

Every cell is spelled out rather than derived from the same ranks the module uses: a test that
recomputed the rule would agree with any rule, including a wrong one.
"""

import uuid

import pytest

from app.models import User, UserRole
from app.services import permissions
from app.services.permissions import HiddenAccountError, NotAllowedError

BUYER = UserRole.BUYER
SELLER = UserRole.SELLER
MODERATOR = UserRole.MODERATOR
ADMIN = UserRole.ADMIN

ROLES = [BUYER, SELLER, MODERATOR, ADMIN]

# (actor, target) pairs where blocking is the actor's to do — everything else is refused
MAY_BLOCK = {
    (MODERATOR, BUYER),
    (MODERATOR, SELLER),
    (ADMIN, BUYER),
    (ADMIN, SELLER),
    (ADMIN, MODERATOR),
}


def account(role: UserRole) -> User:
    return User(id=uuid.uuid4(), email=f"{role.value}@example.com", role=role)


@pytest.mark.parametrize("actor", ROLES)
@pytest.mark.parametrize("target", ROLES)
def test_who_may_block_whom(actor: UserRole, target: UserRole) -> None:
    assert permissions.may_block(actor, target) is ((actor, target) in MAY_BLOCK)


@pytest.mark.parametrize("role", ROLES)
def test_nobody_blocks_an_administrator(role: UserRole) -> None:
    """There is one administrator; an account anyone could bar is not a last resort."""
    assert permissions.may_block(role, ADMIN) is False


@pytest.mark.parametrize("role", ROLES)
def test_nobody_blocks_their_own_rank(role: UserRole) -> None:
    assert permissions.may_block(role, role) is False


@pytest.mark.parametrize("role", ROLES)
def test_only_an_administrator_changes_roles(role: UserRole) -> None:
    assert permissions.may_change_role(role, BUYER) is (role is ADMIN)
    assert permissions.may_change_role(role, SELLER) is (role is ADMIN)


@pytest.mark.parametrize("role", ROLES)
def test_the_administrator_role_is_never_handed_out_by_a_role_change(role: UserRole) -> None:
    """Promoting to admin would make a second one, so no actor may act on an admin account."""
    assert permissions.may_change_role(role, ADMIN) is False


@pytest.mark.parametrize("role", ROLES)
def test_only_an_administrator_invites_moderators(role: UserRole) -> None:
    assert permissions.may_appoint_moderator(role) is (role is ADMIN)


@pytest.mark.parametrize("role", ROLES)
def test_only_an_administrator_reads_the_journal(role: UserRole) -> None:
    assert permissions.may_read_audit_log(role) is (role is ADMIN)


def test_blocking_yourself_is_refused_in_its_own_words() -> None:
    """The rank rule already refuses it; an administrator locking themselves out by accident
    deserves to be told that rather than that they lack rights."""
    admin = account(ADMIN)

    with pytest.raises(NotAllowedError, match="Себя заблокировать нельзя"):
        permissions.ensure_may_block(admin, admin)


def test_a_moderator_may_not_bar_another_moderator() -> None:
    """Refused as "no such account": a refusal that names a level is a refusal that tells."""
    with pytest.raises(HiddenAccountError):
        permissions.ensure_may_block(account(MODERATOR), account(MODERATOR))


def test_blocking_oneself_is_refused_in_its_own_words() -> None:
    """Not hidden: the actor knows perfectly well that they exist."""
    moderator = account(MODERATOR)
    with pytest.raises(NotAllowedError):
        permissions.ensure_may_block(moderator, moderator)


def test_a_moderator_may_not_read_another_moderators_record() -> None:
    with pytest.raises(HiddenAccountError):
        permissions.ensure_may_read(account(MODERATOR), account(MODERATOR))


def test_anybody_may_read_their_own_record() -> None:
    moderator = account(MODERATOR)
    permissions.ensure_may_read(moderator, moderator)


def test_a_moderator_may_bar_a_seller() -> None:
    permissions.ensure_may_block(account(MODERATOR), account(SELLER))


def test_an_administrator_may_bar_a_moderator() -> None:
    permissions.ensure_may_block(account(ADMIN), account(MODERATOR))


def test_changing_your_own_role_is_refused_in_its_own_words() -> None:
    admin = account(ADMIN)

    with pytest.raises(NotAllowedError, match="Свою роль менять нельзя"):
        permissions.ensure_may_change_role(admin, admin)


def test_a_moderator_may_not_change_a_role() -> None:
    with pytest.raises(HiddenAccountError):
        permissions.ensure_may_change_role(account(MODERATOR), account(BUYER))


@pytest.mark.parametrize(
    ("actor", "expected"),
    [
        (BUYER, []),
        (SELLER, []),
        (MODERATOR, [BUYER, SELLER]),
        (ADMIN, [BUYER, SELLER, MODERATOR]),
    ],
)
def test_which_roles_each_actor_can_reach(actor: UserRole, expected: list[UserRole]) -> None:
    """What a staff listing may contain. An administrator never reaches their own rank, so
    the one account nobody may act on is also the one no screen offers buttons for."""
    assert sorted(permissions.reachable_roles(actor)) == sorted(expected)
