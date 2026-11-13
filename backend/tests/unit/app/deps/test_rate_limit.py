"""Which routes carry an allowance, what each one is counted on, and what a refusal looks like.

The numbers in the module are chosen so that nobody doing the thing honestly ever meets them,
and asserting their values here would only write them down twice. What is tested is what breaks
silently: what a limit is keyed on (an address or an account), that two routes never share one
tally, and that a refusal arrives as a 429 with `Retry-After` rather than as a 500.

The key is the part worth arguing about. The second factor is counted on the address on
purpose: by that step the caller already has the password, so counting on the account would
let somebody with a stolen one lock the owner out of their own second factor.
"""

import uuid
from typing import Any, cast

import pytest
from fastapi import Depends, FastAPI, status
from fastapi.testclient import TestClient
from redis.exceptions import RedisError

from app.core.config import Settings, get_settings
from app.core.errors import register_exception_handlers
from app.core.rate_limit import ALLOWED, Decision, GraduatedDelay, SlidingWindow
from app.deps import rate_limit
from app.deps.auth import get_current_user, get_signed_in_user
from app.deps.settings import settings_dep
from app.models import User

ACCOUNT = uuid.uuid4()


class Recording:
    """Remembers the key it was asked about and answers with whatever it was told to."""

    def __init__(self, decision: Decision = ALLOWED) -> None:
        self.decision = decision
        self.keys: list[str] = []

    async def check(self, key: str) -> Decision:
        self.keys.append(key)
        return self.decision


class RecordingDelay:
    def __init__(self, seconds: float = 0.0) -> None:
        self.seconds = seconds
        self.asked: list[str] = []
        self.forgotten: list[str] = []

    async def delay_for(self, key: str) -> float:
        self.asked.append(key)
        return self.seconds

    async def forget(self, key: str) -> None:
        self.forgotten.append(key)


def _limiters(**overrides: Any) -> rate_limit.Limiters:
    fields: dict[str, Any] = {
        name: Recording() for name in rate_limit.Limiters.__dataclass_fields__
    }
    fields["login_by_account"] = RecordingDelay()
    return rate_limit.Limiters(**{**fields, **overrides})


def _recorded(limiters: rate_limit.Limiters, field: str) -> list[str]:
    """The set is typed by what a limiter has to answer, not by who is standing in for it."""
    return cast(Recording, getattr(limiters, field)).keys


def _client(dependency: Any, limiters: rate_limit.Limiters, user: User | None = None) -> TestClient:
    """One road, with exactly the dependency under test standing on it."""
    app = FastAPI()
    register_exception_handlers(app)
    app.state.limiters = limiters
    app.dependency_overrides[settings_dep] = lambda: get_settings()
    if user is not None:
        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[get_signed_in_user] = lambda: user

    @app.post("/guarded", dependencies=[Depends(dependency)])
    async def guarded() -> dict[str, bool]:
        return {"ok": True}

    return TestClient(app, raise_server_exceptions=False)


@pytest.mark.parametrize(
    ("dependency", "field"),
    [
        (rate_limit.limit_login, "login_by_address"),
        (rate_limit.limit_registration, "registration"),
        (rate_limit.limit_reset_request, "reset_request"),
        (rate_limit.limit_reset_confirm, "reset_confirm"),
        (rate_limit.limit_refresh, "refresh"),
        (rate_limit.limit_second_factor, "second_factor"),
    ],
)
def test_a_limit_before_anybody_is_known_is_counted_on_the_address(
    dependency: Any, field: str
) -> None:
    """Before a sign-in there is no account, and where the call came from is all that is known."""
    limiters = _limiters()

    response = _client(dependency, limiters).post("/guarded")

    assert response.status_code == status.HTTP_200_OK
    assert _recorded(limiters, field) == ["testclient"]


@pytest.mark.parametrize(
    ("dependency", "field"),
    [
        (rate_limit.limit_credential_change, "credential_change"),
        (rate_limit.limit_staff_actions, "staff"),
    ],
)
def test_a_limit_on_a_signed_in_action_is_counted_on_the_account(
    dependency: Any, field: str
) -> None:
    """Changing a password and handing out roles come from a known account, and counting them
    on the address would punish a neighbour on a shared one for somebody else's doing."""
    limiters = _limiters()
    user = User(id=ACCOUNT, email="owner@example.com")

    response = _client(dependency, limiters, user=user).post("/guarded")

    assert response.status_code == status.HTTP_200_OK
    assert _recorded(limiters, field) == [str(ACCOUNT)]


def test_the_second_factor_is_not_counted_on_the_account() -> None:
    """Otherwise a stolen password would be enough to lock the owner out of their own second
    factor: somebody else's attempts would spend their allowance."""
    limiters = _limiters()
    user = User(id=ACCOUNT, email="owner@example.com")

    _client(rate_limit.limit_second_factor, limiters, user=user).post("/guarded")

    assert _recorded(limiters, "second_factor") == ["testclient"]
    assert str(ACCOUNT) not in _recorded(limiters, "second_factor")


def test_a_refusal_arrives_as_a_limit_and_not_as_a_breakage() -> None:
    """429 with `Retry-After`, because the caller has to read "later" rather than "broken"."""
    limiters = _limiters(
        login_by_address=Recording(Decision(allowed=False, retry_after_seconds=90))
    )

    response = _client(rate_limit.limit_login, limiters).post("/guarded")

    assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS
    assert response.json()["error"]["code"] == "too_many_requests"
    assert response.headers["Retry-After"] == "90"


def test_a_refusal_says_nothing_about_who_was_refused() -> None:
    """One text for everybody: the answer must not tell whether the account exists."""
    limiters = _limiters(registration=Recording(Decision(allowed=False, retry_after_seconds=1)))

    response = _client(rate_limit.limit_registration, limiters).post("/guarded")

    assert response.json()["error"]["message"] == rate_limit.TOO_MANY


def test_an_address_behind_a_trusted_proxy_is_counted_once_per_sixty_four() -> None:
    """One IPv6 customer is routinely handed a whole /64, so a tally per address would be an
    invitation rather than a limit: the next attempt simply comes from the next address."""
    limiters = _limiters()
    app = FastAPI()
    app.state.limiters = limiters
    trusting = get_settings().model_copy(update={"trusted_proxies": ["127.0.0.1/32"]})
    app.dependency_overrides[settings_dep] = lambda: trusting

    @app.post("/guarded", dependencies=[Depends(rate_limit.limit_login)])
    async def guarded() -> dict[str, bool]:
        return {"ok": True}

    client = TestClient(app, client=("127.0.0.1", 40000))
    client.post("/guarded", headers={"x-forwarded-for": "2001:db8::1"})
    client.post("/guarded", headers={"x-forwarded-for": "2001:db8::dead:beef"})

    assert _recorded(limiters, "login_by_address") == ["2001:db8::/64", "2001:db8::/64"]


async def test_the_per_account_delay_is_keyed_on_what_was_typed() -> None:
    """The account may not exist at all, and the answer must not reveal which case this is.

    These two are not dependencies: the address they are keyed on arrives in the body, and no
    dependency can take a key from there — which is why the sign-in route calls them by hand."""
    limiters = _limiters(login_by_account=RecordingDelay(seconds=2.0))
    app = FastAPI()
    app.state.limiters = limiters
    request: Any = type("Request", (), {"app": app})()

    assert await rate_limit.delay_for_account(request, "typed@example.com") == 2.0
    await rate_limit.forget_account_delay(request, "typed@example.com")

    delay = cast(RecordingDelay, limiters.login_by_account)
    assert delay.asked == ["typed@example.com"]
    assert delay.forgotten == ["typed@example.com"]


def _built(url: str | None) -> rate_limit.Limiters:
    settings: Settings = get_settings().model_copy(update={"redis_url": url})
    return rate_limit.build_limiters(settings)


def test_without_redis_every_tally_is_this_worker_s_own() -> None:
    """Honest for one worker and quietly wrong for two — but only this function knows which it
    built, and nothing above it chooses."""
    built = _built(None)

    assert isinstance(built.login_by_account, GraduatedDelay)
    counted = [value for name, value in vars(built).items() if name != "login_by_account"]
    assert all(isinstance(value, SlidingWindow) for value in counted)


class FakeRedis:
    """A tally that can be told to fall over. Remembers the keys it was counted under."""

    def __init__(self) -> None:
        self.counted: list[str] = []
        self.unreachable = False

    @classmethod
    def from_url(cls, url: str, decode_responses: bool = False) -> "FakeRedis":
        return cls()

    def register_script(self, body: str) -> Any:
        async def run(keys: list[str], args: list[Any]) -> list[Any]:
            if self.unreachable:
                raise RedisError("the tally cannot be reached")
            self.counted.append(keys[0])
            return [1, 0.0, 1]

        return run

    async def delete(self, key: str) -> None:
        self.counted.append(f"drop:{key}")


def _with_a_fake_redis(monkeypatch: pytest.MonkeyPatch) -> tuple[rate_limit.Limiters, FakeRedis]:
    shared = FakeRedis()
    monkeypatch.setattr(
        rate_limit, "Redis", type("Stub", (), {"from_url": staticmethod(lambda *a, **k: shared)})
    )
    return _built("redis://localhost:6379/15"), shared


async def _spend(built: rate_limit.Limiters, key: str) -> list[Any]:
    """Spends one attempt in every tally of the set and hands back their answers."""
    answers: list[Any] = []
    for name, value in vars(built).items():
        if name == "login_by_account":
            answers.append(await value.delay_for(key))
        else:
            answers.append(await value.check(key))
    return answers


async def test_with_redis_the_tally_is_the_shared_one(monkeypatch: pytest.MonkeyPatch) -> None:
    """ "One tally for the platform when `REDIS_URL` says where" is checked by the count really
    going there rather than staying in the process."""
    built, shared = _with_a_fake_redis(monkeypatch)

    await _spend(built, "somebody")

    assert len(shared.counted) == len(vars(built))


async def test_an_unreachable_tally_does_not_take_the_routes_with_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Redis going away used to come out of here as a connection error, and every route with a
    limit answered 500: the limiter, whose job is to keep the platform on its feet under
    pressure, became what made it unavailable. Now a per-worker tally stands behind it."""
    built, shared = _with_a_fake_redis(monkeypatch)
    shared.unreachable = True

    answers = await _spend(built, "somebody")

    assert shared.counted == []
    assert all(answer == 0.0 or answer.allowed for answer in answers), answers


async def test_shared_tallies_do_not_share_a_name(monkeypatch: pytest.MonkeyPatch) -> None:
    """Two routes under one name would add their attempts into one tally — which is exactly how
    the suite once walked into a shared sign-in counter."""
    built, shared = _with_a_fake_redis(monkeypatch)

    await _spend(built, "somebody")

    assert len(shared.counted) == len(set(shared.counted)), shared.counted


def test_the_limiters_are_built_per_application() -> None:
    """So a test gets its own set along with its own application rather than inheriting the
    previous one's tally — otherwise the order of the tests would decide who runs out."""
    first, second = _built(None), _built(None)

    assert first is not second
    assert first.login_by_address is not second.login_by_address
