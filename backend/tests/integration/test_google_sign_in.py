"""Signing in with Google, checked against a Google we control.

Everything here signs ID tokens for real, with a real RSA key, and serves a real JWKS — only
the issuer is ours. A test that stubbed the verification would be checking that the code calls
a function, which is not the thing worth knowing; what is worth knowing is that a token with
the wrong audience, the wrong nonce, no signature or an unconfirmed address is refused.
"""

import json
import time
import uuid
from collections.abc import AsyncIterator
from typing import Any

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.db.session import get_session
from app.deps.settings import settings_dep
from app.main import create_app
from app.models import Business, User, UserIdentity, UserRole
from tests.integration.conftest import csrf_headers, register_buyer

pytestmark = pytest.mark.integration

CLIENT_ID = "allstore-test.apps.googleusercontent.com"
ISSUER = "https://accounts.google.com"
START = "/api/v1/auth/google/start"
CALLBACK = "/api/v1/auth/google/callback"
KID = "test-key"


@pytest.fixture(scope="module")
def signing_key() -> rsa.RSAPrivateKey:
    """One key for the module: generating RSA is slow enough to notice per test."""
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _jwks(key: rsa.RSAPrivateKey) -> dict[str, Any]:
    public = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()))
    return {"keys": [{**public, "kid": KID, "use": "sig", "alg": "RS256"}]}


def _id_token(key: rsa.RSAPrivateKey, **overrides: Any) -> str:
    claims = {
        "iss": ISSUER,
        "aud": CLIENT_ID,
        "sub": "google-subject-1",
        "email": "person@gmail.com",
        "email_verified": True,
        "nonce": "the-nonce",
        "iat": int(time.time()),
        "exp": int(time.time()) + 300,
    }
    claims.update(overrides)
    return jwt.encode(claims, key, algorithm="RS256", headers={"kid": KID})


@pytest.fixture
def google(monkeypatch: pytest.MonkeyPatch, signing_key: rsa.RSAPrivateKey) -> Any:
    """Stands in for accounts.google.com, serving whatever the test wants it to say."""
    state: dict[str, Any] = {"id_token": None, "token_status": 200}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("openid-configuration"):
            return httpx.Response(
                200,
                json={
                    "authorization_endpoint": f"{ISSUER}/o/oauth2/v2/auth",
                    "token_endpoint": f"{ISSUER}/token",
                    "jwks_uri": f"{ISSUER}/certs",
                },
                request=request,
            )
        if request.url.path.endswith("/certs"):
            return httpx.Response(200, json=_jwks(signing_key), request=request)
        if state["token_status"] != 200:
            return httpx.Response(state["token_status"], json={}, request=request)
        return httpx.Response(200, json={"id_token": state["id_token"]}, request=request)

    original = httpx.AsyncClient.__init__

    def patched(self: httpx.AsyncClient, **kwargs: Any) -> None:
        original(self, transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "__init__", patched)

    def says(**overrides: Any) -> None:
        state["id_token"] = _id_token(signing_key, **overrides)

    says()

    def refuses(status: int) -> None:
        state["token_status"] = status

    says.refuses = refuses  # type: ignore[attr-defined]
    return says


def _settings() -> Settings:
    return get_settings().model_copy(
        update={
            "google_client_id": CLIENT_ID,
            "google_client_secret": get_settings().secret_key,
            "site_url": "http://test",
        }
    )


@pytest.fixture
async def client(session: AsyncSession) -> AsyncIterator[AsyncClient]:
    app = create_app()

    async def _use_test_session() -> AsyncSession:
        return session

    app.dependency_overrides[get_session] = _use_test_session
    app.dependency_overrides[settings_dep] = _settings
    async with AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as made:
        yield made


async def _handshake(client: AsyncClient, role: str = "buyer") -> str:
    """Walks the first half and returns the state the server expects back."""
    leaving = await client.get(START, params={"role": role}, follow_redirects=False)
    assert leaving.status_code == 307
    return httpx.URL(leaving.headers["location"]).params["state"]


async def test_the_journey_out_carries_pkce_and_a_nonce(client: AsyncClient, google: Any) -> None:
    leaving = await client.get(START, follow_redirects=False)

    sent_to = httpx.URL(leaving.headers["location"])
    assert sent_to.params["code_challenge_method"] == "S256"
    assert sent_to.params["code_challenge"]
    assert sent_to.params["nonce"]
    assert sent_to.params["scope"] == "openid email profile"


async def test_signing_in_creates_an_account_and_a_session(
    client: AsyncClient, google: Any, session: AsyncSession
) -> None:
    state = await _handshake(client)
    google(nonce=_nonce(client))

    landed = await client.get(
        CALLBACK, params={"code": "a-code", "state": state}, follow_redirects=False
    )

    assert landed.status_code == 303
    user = (await session.execute(select(User))).scalars().one()
    assert user.email == "person@gmail.com"
    # Google says it checked the address, which is the same thing our own letter establishes
    assert user.email_verified_at is not None
    assert user.password_hash is None
    assert (await client.get("/api/v1/users/me")).status_code == 200


async def test_the_same_google_account_opens_the_same_platform_account(
    client: AsyncClient, google: Any, session: AsyncSession
) -> None:
    state = await _handshake(client)
    google(nonce=_nonce(client))
    await client.get(CALLBACK, params={"code": "a", "state": state}, follow_redirects=False)
    client.cookies.clear()

    state = await _handshake(client)
    google(nonce=_nonce(client), email="renamed@gmail.com")
    await client.get(CALLBACK, params={"code": "b", "state": state}, follow_redirects=False)

    # the subject is the identity; the address on it is a label its owner may change
    assert len((await session.execute(select(User))).scalars().all()) == 1


async def test_an_address_with_a_password_account_is_not_swallowed(
    client: AsyncClient, google: Any, session: AsyncSession
) -> None:
    """Joining them would mean anybody who can persuade a provider to assert an address can
    take the account behind it."""
    await register_buyer(client, email="person@gmail.com")
    client.cookies.clear()
    state = await _handshake(client)
    google(nonce=_nonce(client))

    refused = await client.get(
        CALLBACK, params={"code": "a", "state": state}, follow_redirects=False
    )

    assert refused.status_code == 409
    assert refused.json()["error"]["code"] == "link_from_settings"
    assert (await session.execute(select(UserIdentity))).scalars().all() == []


@pytest.mark.parametrize(
    ("overrides", "why"),
    [
        ({"aud": "somebody-elses-client"}, "a token minted for another application"),
        ({"iss": "https://evil.example"}, "a token from an issuer we never trusted"),
        ({"nonce": "not-the-one-we-sent"}, "a token obtained somewhere else and replayed"),
        ({"email_verified": False}, "an address Google itself has not confirmed"),
        ({"exp": int(time.time()) - 60}, "a token that has expired"),
    ],
)
async def test_a_token_that_fails_any_check_is_refused(
    client: AsyncClient, google: Any, overrides: dict[str, Any], why: str
) -> None:
    state = await _handshake(client)
    # the nonce is the one we sent unless this case is specifically about replacing it
    google(**{"nonce": _nonce(client), **overrides})

    refused = await client.get(
        CALLBACK, params={"code": "a", "state": state}, follow_redirects=False
    )

    assert refused.status_code == 403, why


async def test_a_code_cannot_be_spent_twice(client: AsyncClient, google: Any) -> None:
    """The last of the negative set the plan asked for.

    Google itself refuses a reused code, but relying on that would be relying on somebody
    else's server to hold our line. The handshake cookie is deleted on the way out and the
    state has to match what it said, so a second arrival with the same code has nothing to be
    checked against — which is the property worth having a test for, because it holds whether
    or not the provider is doing its job.
    """
    state = await _handshake(client)
    google(nonce=_nonce(client))
    first = await client.get(CALLBACK, params={"code": "a", "state": state}, follow_redirects=False)
    assert first.status_code == 303

    again = await client.get(CALLBACK, params={"code": "a", "state": state}, follow_redirects=False)

    assert again.status_code == 403


async def test_a_state_that_does_not_match_is_refused(client: AsyncClient, google: Any) -> None:
    """Without it, anybody could hand somebody else's code to somebody else's session."""
    await _handshake(client)
    google(nonce=_nonce(client))

    refused = await client.get(
        CALLBACK, params={"code": "a", "state": "not-the-state"}, follow_redirects=False
    )

    assert refused.status_code == 403


async def test_a_return_with_no_handshake_at_all_is_refused(
    client: AsyncClient, google: Any
) -> None:
    refused = await client.get(
        CALLBACK, params={"code": "a", "state": "invented"}, follow_redirects=False
    )

    assert refused.status_code == 403


async def test_nobody_becomes_a_moderator_this_way(client: AsyncClient, google: Any) -> None:
    """A provider asserting an address is not a grant of authority."""
    refused = await client.get(START, params={"role": "moderator"}, follow_redirects=False)

    assert refused.status_code == 422


def _nonce(client: AsyncClient) -> str:
    """Reads back the nonce the server wrote into its own sealed cookie."""
    from app.api.google import HANDSHAKE_COOKIE, _unseal

    sealed = client.cookies.get(HANDSHAKE_COOKIE)
    payload = _unseal(_settings(), sealed)
    assert payload is not None
    return payload["nonce"]


async def test_the_handshake_cookie_cannot_be_forged(client: AsyncClient, google: Any) -> None:
    """A cookie the caller can write is a cookie the caller can use to answer our challenge."""
    from app.api.google import HANDSHAKE_COOKIE

    forged = json.dumps({"state": "mine", "nonce": "mine", "verifier": "mine", "role": "buyer"})
    client.cookies.set(HANDSHAKE_COOKIE, f"deadbeef.{forged}")

    refused = await client.get(
        CALLBACK, params={"code": "a", "state": "mine"}, follow_redirects=False
    )

    assert refused.status_code == 403


async def test_with_no_credentials_the_way_in_is_not_offered(session: AsyncSession) -> None:
    app = create_app()

    async def _use_test_session() -> AsyncSession:
        return session

    app.dependency_overrides[get_session] = _use_test_session
    async with AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as bare:
        refused = await bare.get(START, follow_redirects=False)

    assert refused.status_code == 403
    assert refused.json()["error"]["code"] == "google_not_configured"


async def test_an_account_opened_with_google_cannot_be_signed_into_with_a_password(
    client: AsyncClient, google: Any
) -> None:
    """And is told nothing about why: saying "that one has no password" tells a stranger how
    this person signs in."""
    state = await _handshake(client)
    google(nonce=_nonce(client))
    await client.get(CALLBACK, params={"code": "a", "state": state}, follow_redirects=False)
    client.cookies.clear()

    refused = await client.post(
        "/api/v1/auth/login", json={"email": "person@gmail.com", "password": "anything-at-all-1"}
    )

    assert refused.status_code == 401
    assert refused.json()["error"]["code"] == "invalid_credentials"


async def test_the_last_way_in_cannot_be_detached(
    client: AsyncClient, google: Any, session: AsyncSession
) -> None:
    """An account with no password and no identity is one nobody can open, its owner included."""
    state = await _handshake(client)
    google(nonce=_nonce(client))
    await client.get(CALLBACK, params={"code": "a", "state": state}, follow_redirects=False)
    identity = (await session.execute(select(UserIdentity))).scalars().one()

    refused = await client.delete(
        f"/api/v1/auth/google/identities/{identity.id}", headers=csrf_headers(client)
    )

    assert refused.status_code == 409


async def test_a_seller_arrives_with_an_account_and_no_shop(
    client: AsyncClient, google: Any, session: AsyncSession
) -> None:
    """Google knows an address; a business needs a legal name, and both of its name columns
    are NOT NULL. So the shop cannot be created here, and the seller is sent to answer for it
    — the cabinet redirects to the onboarding screen on exactly this state."""
    state = await _handshake(client, role="seller")
    google(nonce=_nonce(client))

    await client.get(CALLBACK, params={"code": "a", "state": state}, follow_redirects=False)

    user = (await session.execute(select(User))).scalars().one()
    assert user.role is UserRole.SELLER
    assert (await session.execute(select(Business))).scalars().all() == []
    # and the way out is open: the onboarding route answers this account
    opened = await client.post(
        "/api/v1/users/me/business",
        json={"legal_name": "ИП Петров", "display_name": "Лавка"},
        headers=csrf_headers(client),
    )
    assert opened.status_code == 201


async def test_attaching_and_detaching_a_way_in_is_reported_to_the_owner(
    client: AsyncClient, google: Any, monkeypatch: pytest.MonkeyPatch, session: AsyncSession
) -> None:
    """An attachment nobody asked for is the one change an intruder makes that leaves the
    password working — so the owner notices nothing unless they are told."""
    from app.services import notifications

    caught: list[Any] = []

    def fake_deliver(settings: object, letter: Any) -> None:
        caught.append(letter)

    monkeypatch.setattr(notifications, "deliver", fake_deliver)
    await register_buyer(client, email="owner@example.com")
    caught.clear()  # registration writes its own letter, and this test is not about that one
    state = await _handshake_for_linking(client)
    google(nonce=_nonce(client))
    await client.get(CALLBACK, params={"code": "a", "state": state}, follow_redirects=False)
    identity = (await session.execute(select(UserIdentity))).scalars().one()

    await client.delete(
        f"/api/v1/auth/google/identities/{identity.id}", headers=csrf_headers(client)
    )

    assert [letter.to for letter in caught] == ["owner@example.com", "owner@example.com"]
    assert "привязан" in caught[0].body
    assert "отвязан" in caught[1].body


async def _handshake_for_linking(client: AsyncClient) -> str:
    """The same journey as `_handshake`, started from inside an account that already exists."""
    leaving = await client.get("/api/v1/auth/google/link", follow_redirects=False)
    assert leaving.status_code == 307
    return httpx.URL(leaving.headers["location"]).params["state"]


async def test_an_identity_belonging_to_somebody_else_is_not_there(
    client: AsyncClient, google: Any
) -> None:
    state = await _handshake(client)
    google(nonce=_nonce(client))
    await client.get(CALLBACK, params={"code": "a", "state": state}, follow_redirects=False)

    refused = await client.delete(
        f"/api/v1/auth/google/identities/{uuid.uuid4()}", headers=csrf_headers(client)
    )

    assert refused.status_code == 403
