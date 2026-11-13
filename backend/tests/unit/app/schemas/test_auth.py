"""What a form may send to the routes that create, open and change an account.

These are the only rules that run before anything is read from the database, so they are the
rules a person meets first. Two of them matter beyond the form itself: an address is one
account however it was typed, and a secret is never answered back.
"""

import uuid
from datetime import UTC, datetime

import pytest
from pydantic import SecretStr, ValidationError

from app.core.security import MAX_PASSWORD_LENGTH, MIN_PASSWORD_LENGTH
from app.models import BusinessStatus, UserRole, UserStatus
from app.models.business import Business as BusinessModel
from app.models.moderation import BusinessModerationReview
from app.schemas.auth import (
    BusinessOnboardingRequest,
    BusinessRead,
    BuyerRegisterRequest,
    LoginRequest,
    PasswordChangeRequest,
    SellerRegisterRequest,
    TotpCodeRequest,
    UserRead,
)


@pytest.mark.parametrize(
    "typed",
    ["Person@Example.AM", "  person@example.am  ", "PERSON@EXAMPLE.AM"],
)
def test_an_address_is_one_account_however_it_was_typed(typed: str) -> None:
    """Otherwise the same person registers twice and neither of the two can be signed into."""
    assert LoginRequest(email=typed, password=SecretStr("x")).normalized_email == (
        "person@example.am"
    )


def test_an_address_that_is_not_one_is_refused() -> None:
    with pytest.raises(ValidationError):
        LoginRequest(email="person at example", password=SecretStr("x"))


@pytest.mark.parametrize("length", [MIN_PASSWORD_LENGTH, MAX_PASSWORD_LENGTH])
def test_a_password_of_an_allowed_length_is_taken(length: int) -> None:
    account = BuyerRegisterRequest(email="person@example.am", password=SecretStr("a" * length))

    assert len(account.password.get_secret_value()) == length


@pytest.mark.parametrize("length", [MIN_PASSWORD_LENGTH - 1, MAX_PASSWORD_LENGTH + 1])
def test_a_password_outside_it_is_refused(length: int) -> None:
    """The ceiling is as deliberate as the floor: argon2 is paid for per byte, and a megabyte
    of password is a way to spend the machine's time rather than a way to be safe."""
    with pytest.raises(ValidationError):
        BuyerRegisterRequest(email="person@example.am", password=SecretStr("a" * length))


def test_a_password_is_not_answered_back() -> None:
    """`SecretStr` rather than `str` everywhere a secret travels: a form that echoes its own
    body into a log — and something always does — must not put one there."""
    account = BuyerRegisterRequest(email="person@example.am", password=SecretStr("a" * 12))

    assert "a" * 12 not in repr(account)
    assert "a" * 12 not in str(account.password)


@pytest.mark.parametrize("typed", ["+37410123456", "37410123456", "123456"])
def test_a_telephone_number_in_a_shape_somebody_could_dial(typed: str) -> None:
    assert (
        BuyerRegisterRequest(
            email="person@example.am", password=SecretStr("a" * 12), phone=typed
        ).phone
        == typed
    )


@pytest.mark.parametrize("typed", ["12345", "+374 10 123 456", "not a number", "+" + "9" * 21])
def test_a_telephone_number_in_no_shape_at_all_is_refused(typed: str) -> None:
    with pytest.raises(ValidationError):
        BuyerRegisterRequest(email="person@example.am", password=SecretStr("a" * 12), phone=typed)


def test_a_telephone_number_is_optional_because_nobody_was_asked_for_one() -> None:
    assert (
        BuyerRegisterRequest(email="person@example.am", password=SecretStr("a" * 12)).phone is None
    )


def test_a_shop_name_arrives_without_the_whitespace_around_it() -> None:
    """A trailing space is what a paste leaves behind, and it would be shown to buyers."""
    shop = BusinessOnboardingRequest(legal_name="  ООО Ромашка  ", display_name=" Ромашка ")

    assert shop.legal_name == "ООО Ромашка"
    assert shop.display_name == "Ромашка"


@pytest.mark.parametrize("name", ["", " ", "a", "  a  "])
def test_a_shop_name_of_one_character_is_not_a_name(name: str) -> None:
    """Whitespace is stripped before the length is counted, so a space is not a letter."""
    with pytest.raises(ValidationError):
        BusinessOnboardingRequest(legal_name=name, display_name="Ромашка")


def test_a_seller_can_answer_both_halves_at_once() -> None:
    """One form: the account and the shop, because a password registration can ask for both."""
    seller = SellerRegisterRequest(
        email="shop@example.am",
        password=SecretStr("a" * 12),
        legal_name="ООО Ромашка",
        display_name="Ромашка",
    )

    assert seller.normalized_email == "shop@example.am"
    assert seller.display_name == "Ромашка"


def test_changing_a_password_asks_for_the_current_one() -> None:
    """Even when the account owes a change: a session left open on somebody else's screen must
    not be enough to take the account over."""
    # as a dict: a call missing the field would not compile, and a body missing it arrives
    body: dict[str, object] = {"password": SecretStr("a" * 12)}
    with pytest.raises(ValidationError):
        PasswordChangeRequest(**body)


@pytest.mark.parametrize("code", ["123456", " 123456 ", "a" * 32])
def test_a_second_factor_code_may_be_either_shape(code: str) -> None:
    """Six digits from an application or one of the recovery codes. Refusing the second shape
    here would mean the form could not accept it at all; which one it is, totp.py decides."""
    assert TotpCodeRequest(code=code).code == code.strip()


@pytest.mark.parametrize("code", ["12345", "a" * 33])
def test_a_second_factor_code_outside_both_shapes_is_refused(code: str) -> None:
    with pytest.raises(ValidationError):
        TotpCodeRequest(code=code)


def _account() -> UserRead:
    return UserRead(
        id=uuid.uuid4(),
        email="person@example.am",
        phone=None,
        role=UserRole.BUYER,
        status=UserStatus.ACTIVE,
        last_login_at=None,
        must_change_password=False,
        password_handed_over_at=None,
        email_verified_at=None,
        created_at=datetime.now(UTC),
    )


def test_what_an_account_tells_the_client_about_itself() -> None:
    """No hash, no sessions, no second-factor secret — a client never needs any of them, and
    the way to be sure none of them leaks is for the shape not to have a place for one."""
    fields = set(UserRead.model_fields)

    assert "password_hash" not in fields
    assert fields == {
        "id",
        "email",
        "phone",
        "role",
        "status",
        "last_login_at",
        "must_change_password",
        "password_handed_over_at",
        "email_verified_at",
        "created_at",
    }
    assert _account().must_change_password is False


def test_a_shop_carries_the_reason_it_is_where_it_is() -> None:
    """A refusal the seller cannot read is a refusal they cannot answer — and answering it is
    the whole point of `rejected` being a status apart from `blocked`."""
    business = BusinessModel(
        id=uuid.uuid4(),
        legal_name="ООО Ромашка",
        display_name="Ромашка",
        description=None,
        status=BusinessStatus.REJECTED,
        created_at=datetime.now(UTC),
    )
    business.reviews = [
        BusinessModerationReview(reason=None),
        BusinessModerationReview(reason="Нет документов"),
    ]

    assert BusinessRead.of(business).status_reason == "Нет документов"


def test_a_shop_nobody_said_anything_about_carries_no_reason() -> None:
    """And the plain read does not reach for the history at all: `reviews` is lazy, and the
    catalogue loads one business per card and needs none of it."""
    business = BusinessModel(
        id=uuid.uuid4(),
        legal_name="ООО Ромашка",
        display_name="Ромашка",
        description=None,
        status=BusinessStatus.ACTIVE,
        created_at=datetime.now(UTC),
    )

    assert BusinessRead.model_validate(business).status_reason is None
