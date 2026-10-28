from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import PasswordResetToken, RefreshToken, User
from app.services import auth as auth_service
from tests.integration.conftest import login, register_buyer

pytestmark = pytest.mark.integration

EMAIL = "buyer@example.com"
NEW_PASSWORD = "brand-new-password-1"


@pytest.fixture
def sent_tokens(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str]]:
    """The email provider arrives in stage 8; until then the reset token is captured here."""
    captured: list[tuple[str, str]] = []

    async def fake_send(email: str, token: str) -> None:
        captured.append((email, token))

    monkeypatch.setattr(auth_service, "send_password_reset_email", fake_send)
    return captured


async def request_reset(client: AsyncClient, email: str) -> int:
    response = await client.post("/api/v1/auth/password-reset/request", json={"email": email})
    return response.status_code


async def test_reset_request_answers_the_same_for_unknown_email(
    api_client: AsyncClient, sent_tokens: list[tuple[str, str]]
) -> None:
    await register_buyer(api_client)

    known = await api_client.post("/api/v1/auth/password-reset/request", json={"email": EMAIL})
    unknown = await api_client.post(
        "/api/v1/auth/password-reset/request", json={"email": "nobody@example.com"}
    )

    assert known.status_code == unknown.status_code == 202
    assert known.json() == unknown.json()
    assert [email for email, _ in sent_tokens] == [EMAIL]


async def test_reset_changes_the_password(
    api_client: AsyncClient, sent_tokens: list[tuple[str, str]]
) -> None:
    await register_buyer(api_client)
    await request_reset(api_client, EMAIL)
    _, token = sent_tokens[0]

    confirm = await api_client.post(
        "/api/v1/auth/password-reset/confirm", json={"token": token, "password": NEW_PASSWORD}
    )

    assert confirm.status_code == 200
    api_client.cookies.clear()
    assert (await login(api_client, EMAIL, NEW_PASSWORD)).status_code == 200


async def test_reset_clears_the_demand_to_choose_a_password(
    api_client: AsyncClient, session: AsyncSession, sent_tokens: list[tuple[str, str]]
) -> None:
    """Whatever the old password was, this one the owner chose themselves."""
    await register_buyer(api_client)
    user = (await session.execute(select(User).where(User.email == EMAIL))).scalars().one()
    user.must_change_password = True
    await session.flush()
    await request_reset(api_client, EMAIL)
    _, token = sent_tokens[0]

    await api_client.post(
        "/api/v1/auth/password-reset/confirm", json={"token": token, "password": NEW_PASSWORD}
    )

    await session.refresh(user)
    assert user.must_change_password is False


async def test_old_password_stops_working_after_reset(
    api_client: AsyncClient, sent_tokens: list[tuple[str, str]]
) -> None:
    await register_buyer(api_client)
    await request_reset(api_client, EMAIL)
    await api_client.post(
        "/api/v1/auth/password-reset/confirm",
        json={"token": sent_tokens[0][1], "password": NEW_PASSWORD},
    )
    api_client.cookies.clear()

    response = await login(api_client, EMAIL, "buyer-password-1")

    assert response.status_code == 401


async def test_reset_revokes_existing_sessions(
    api_client: AsyncClient, session: AsyncSession, sent_tokens: list[tuple[str, str]]
) -> None:
    """A reset is what a person does after a theft — the thief's session must not survive it."""
    await register_buyer(api_client)
    await request_reset(api_client, EMAIL)
    await api_client.post(
        "/api/v1/auth/password-reset/confirm",
        json={"token": sent_tokens[0][1], "password": NEW_PASSWORD},
    )

    tokens = (await session.execute(select(RefreshToken))).scalars().all()
    assert tokens
    assert all(token.revoked_at is not None for token in tokens)


async def test_a_token_works_only_once(
    api_client: AsyncClient, sent_tokens: list[tuple[str, str]]
) -> None:
    await register_buyer(api_client)
    await request_reset(api_client, EMAIL)
    token = sent_tokens[0][1]
    await api_client.post(
        "/api/v1/auth/password-reset/confirm", json={"token": token, "password": NEW_PASSWORD}
    )

    second = await api_client.post(
        "/api/v1/auth/password-reset/confirm",
        json={"token": token, "password": "another-password-1"},
    )

    assert second.status_code == 401
    assert second.json()["error"]["code"] == "invalid_reset_token"


async def test_expired_token_is_refused(
    api_client: AsyncClient, session: AsyncSession, sent_tokens: list[tuple[str, str]]
) -> None:
    await register_buyer(api_client)
    await request_reset(api_client, EMAIL)
    stored = (await session.execute(select(PasswordResetToken))).scalar_one()
    stored.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    await session.flush()

    response = await api_client.post(
        "/api/v1/auth/password-reset/confirm",
        json={"token": sent_tokens[0][1], "password": NEW_PASSWORD},
    )

    assert response.status_code == 401


async def test_unknown_token_is_refused(api_client: AsyncClient) -> None:
    response = await api_client.post(
        "/api/v1/auth/password-reset/confirm",
        json={"token": "made-up-token", "password": NEW_PASSWORD},
    )

    assert response.status_code == 401


async def test_short_new_password_is_rejected(
    api_client: AsyncClient, sent_tokens: list[tuple[str, str]]
) -> None:
    await register_buyer(api_client)
    await request_reset(api_client, EMAIL)

    response = await api_client.post(
        "/api/v1/auth/password-reset/confirm",
        json={"token": sent_tokens[0][1], "password": "short"},
    )

    assert response.status_code == 422
