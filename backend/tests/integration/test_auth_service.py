import pytest
from argon2 import PasswordHasher
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import AccountNotActiveError
from app.core.security import verify_password
from app.models import UserRole, UserStatus
from app.schemas.auth import BuyerRegisterRequest, SellerRegisterRequest
from app.services import auth as auth_service
from app.services import sessions as session_service

pytestmark = pytest.mark.integration

PASSWORD = "service-password-1"


def buyer_request(**overrides: object) -> BuyerRegisterRequest:
    data: dict[str, object] = {"email": "svc-buyer@example.com", "password": PASSWORD}
    data.update(overrides)
    return BuyerRegisterRequest.model_validate(data)


async def test_registration_stores_only_a_hash(session: AsyncSession) -> None:
    user = await auth_service.register_buyer(session, buyer_request())

    assert user.password_hash != PASSWORD
    assert verify_password(PASSWORD, user.password_hash)


async def test_registration_reports_a_taken_address_inwards_only(
    session: AsyncSession,
) -> None:
    """The service says so; the route does not.

    `AddressAlreadyTaken` exists so the API knows which person to write to — the one who
    already holds the address, not the one who typed it. It never reaches a caller: both
    outcomes get the same sentence, see api/auth.py.
    """
    await auth_service.register_buyer(session, buyer_request())

    with pytest.raises(auth_service.AddressAlreadyTaken):
        await auth_service.register_buyer(session, buyer_request())


async def test_seller_registration_links_user_and_business(session: AsyncSession) -> None:
    request = SellerRegisterRequest.model_validate(
        {
            "email": "svc-seller@example.com",
            "password": PASSWORD,
            "legal_name": "ООО Тест",
            "display_name": "Тест",
        }
    )

    user, business = await auth_service.register_seller(session, request)

    assert user.role is UserRole.SELLER
    assert business.owner_user_id == user.id


async def test_authenticate_returns_the_user(session: AsyncSession) -> None:
    await auth_service.register_buyer(session, buyer_request())

    user = await auth_service.authenticate(session, "svc-buyer@example.com", PASSWORD)

    assert user.email == "svc-buyer@example.com"


async def test_authenticate_rejects_a_wrong_password(session: AsyncSession) -> None:
    await auth_service.register_buyer(session, buyer_request())

    with pytest.raises(auth_service.InvalidCredentialsError):
        await auth_service.authenticate(session, "svc-buyer@example.com", "wrong-password-1")


async def test_authenticate_rejects_an_unknown_email(session: AsyncSession) -> None:
    with pytest.raises(auth_service.InvalidCredentialsError):
        await auth_service.authenticate(session, "nobody@example.com", PASSWORD)


async def test_authenticate_refuses_a_suspended_account(session: AsyncSession) -> None:
    user = await auth_service.register_buyer(session, buyer_request())
    user.status = UserStatus.SUSPENDED
    await session.flush()

    with pytest.raises(AccountNotActiveError):
        await auth_service.authenticate(session, "svc-buyer@example.com", PASSWORD)


async def test_login_upgrades_a_hash_made_with_weaker_parameters(session: AsyncSession) -> None:
    """The point of ADR 0002: raising the cost later must not require a password reset."""
    user = await auth_service.register_buyer(session, buyer_request())
    user.password_hash = PasswordHasher(time_cost=1, memory_cost=8, parallelism=1).hash(PASSWORD)
    await session.flush()
    weak_hash = user.password_hash

    await auth_service.authenticate(session, "svc-buyer@example.com", PASSWORD)

    assert user.password_hash != weak_hash
    assert verify_password(PASSWORD, user.password_hash)


async def test_a_session_and_its_csrf_token_are_not_the_same_value(
    session: AsyncSession,
) -> None:
    """One is a credential the browser never reads, the other is one it has to echo back."""
    user = await auth_service.register_buyer(session, buyer_request())

    issued = await session_service.open_session(session, get_settings(), user)

    assert issued.token != issued.csrf_token
