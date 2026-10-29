"""Which routes have an allowance, how wide it is, and what each one is keyed on.

The numbers below are chosen so that nobody doing the thing honestly ever meets them. A
person signs in once, mistypes it twice, asks for one reset link; the limits sit an order of
magnitude above that. They are not tuned to stop a determined attacker — the secrets are long
and random and `services/auth.py` refuses wrong ones on its own. They are here so that a
flood costs the sender something, and so that `/auth/login` cannot be used to spend the whole
machine's CPU on argon2 for free.

What each one is keyed on is the part worth arguing about, and it is argued in place.
"""

from dataclasses import dataclass

from fastapi import Request
from redis.asyncio import Redis

from app.core.client_ip import client_ip
from app.core.config import Settings
from app.core.errors import TooManyRequestsError
from app.core.rate_limit import (
    Allowance,
    Delay,
    DelayWithALocalFallback,
    GraduatedDelay,
    SharedDelay,
    SharedWindow,
    SlidingWindow,
    WithALocalFallback,
)
from app.deps.auth import CurrentUser, SettingsDep, SignedInUser

MINUTE = 60.0
HOUR = 60.0 * MINUTE

# Signing in: generous, because one person at one address may hold several accounts and a
# household shares an address. The narrow guard on guessing is the per-account delay below,
# not this.
LOGIN_ATTEMPTS = 30
LOGIN_WINDOW = 5 * MINUTE

# Per account, and a delay rather than a refusal — see GraduatedDelay. Three free attempts is
# the typo budget; after that each guess costs the sender twice the previous one.
LOGIN_FREE_ATTEMPTS = 3
LOGIN_DELAY_WINDOW = 15 * MINUTE
LOGIN_DELAY_STEP = 0.5
LOGIN_DELAY_CAP = 8.0

# Registering is a once-in-a-lifetime act for a person and a bulk one for a script.
REGISTRATION_ATTEMPTS = 10
REGISTRATION_WINDOW = HOUR

# Asking for a reset link: somebody who lost their password asks once, maybe twice when the
# letter is slow. A flood here is somebody else's inbox being used as a weapon.
RESET_REQUEST_ATTEMPTS = 5
RESET_REQUEST_WINDOW = 15 * MINUTE

# Spending one: the token is 32 random bytes, so this is about the cost of the flood rather
# than about the guess ever landing.
RESET_CONFIRM_ATTEMPTS = 20
RESET_CONFIRM_WINDOW = 15 * MINUTE

# Renewing a session. Several tabs renew independently, so this is well above what one
# person's browser does and still far below a loop.
REFRESH_ATTEMPTS = 60
REFRESH_WINDOW = 5 * MINUTE

# Changing a password or a login, keyed on the account rather than the address: this is a
# signed-in action, so the account is known and is the thing worth limiting.
CREDENTIAL_CHANGE_ATTEMPTS = 10
CREDENTIAL_CHANGE_WINDOW = 15 * MINUTE

# Appointing moderators and handing out their passwords, keyed on the administrator. There is
# exactly one of them and they do this rarely.
STAFF_ATTEMPTS = 20
STAFF_WINDOW = HOUR

TOO_MANY = "Слишком много попыток, попробуйте позже"


@dataclass(frozen=True)
class Limiters:
    """Built once per application, so each process keeps its own tally and a test gets a
    fresh set with its app rather than inheriting the previous test's."""

    login_by_address: Allowance
    login_by_account: Delay
    registration: Allowance
    reset_request: Allowance
    reset_confirm: Allowance
    refresh: Allowance
    credential_change: Allowance
    staff: Allowance


def build_limiters(settings: Settings) -> Limiters:
    """One tally for the platform when `REDIS_URL` says where, one per worker otherwise.

    The in-process set is honest for a single worker and quietly wrong for two: each keeps its
    own count, so the allowance doubles without anybody changing a number. Nothing above this
    function knows which it got.
    """
    if not settings.redis_url:
        return Limiters(
            login_by_address=SlidingWindow(LOGIN_ATTEMPTS, LOGIN_WINDOW),
            login_by_account=GraduatedDelay(
                LOGIN_FREE_ATTEMPTS, LOGIN_DELAY_WINDOW, LOGIN_DELAY_STEP, LOGIN_DELAY_CAP
            ),
            registration=SlidingWindow(REGISTRATION_ATTEMPTS, REGISTRATION_WINDOW),
            reset_request=SlidingWindow(RESET_REQUEST_ATTEMPTS, RESET_REQUEST_WINDOW),
            reset_confirm=SlidingWindow(RESET_CONFIRM_ATTEMPTS, RESET_CONFIRM_WINDOW),
            refresh=SlidingWindow(REFRESH_ATTEMPTS, REFRESH_WINDOW),
            credential_change=SlidingWindow(CREDENTIAL_CHANGE_ATTEMPTS, CREDENTIAL_CHANGE_WINDOW),
            staff=SlidingWindow(STAFF_ATTEMPTS, STAFF_WINDOW),
        )
    shared = Redis.from_url(settings.redis_url, decode_responses=True)

    def window(name: str, limit: int, seconds: float) -> Allowance:
        """One tally on Redis, with this worker's own standing behind it.

        Redis going away used to come out of these dependencies as a connection error, so
        every route carrying a limit answered 500 — the limiter, whose purpose is to keep the
        platform usable under pressure, became what made it unusable.
        """
        return WithALocalFallback(
            SharedWindow(shared, name, limit, seconds), SlidingWindow(limit, seconds)
        )

    return Limiters(
        login_by_address=window("login", LOGIN_ATTEMPTS, LOGIN_WINDOW),
        login_by_account=DelayWithALocalFallback(
            SharedDelay(
                shared,
                "login-account",
                LOGIN_FREE_ATTEMPTS,
                LOGIN_DELAY_WINDOW,
                LOGIN_DELAY_STEP,
                LOGIN_DELAY_CAP,
            ),
            GraduatedDelay(
                LOGIN_FREE_ATTEMPTS, LOGIN_DELAY_WINDOW, LOGIN_DELAY_STEP, LOGIN_DELAY_CAP
            ),
        ),
        registration=window("register", REGISTRATION_ATTEMPTS, REGISTRATION_WINDOW),
        reset_request=window("reset", RESET_REQUEST_ATTEMPTS, RESET_REQUEST_WINDOW),
        reset_confirm=window("reset-confirm", RESET_CONFIRM_ATTEMPTS, RESET_CONFIRM_WINDOW),
        refresh=window("renew", REFRESH_ATTEMPTS, REFRESH_WINDOW),
        credential_change=window(
            "credentials", CREDENTIAL_CHANGE_ATTEMPTS, CREDENTIAL_CHANGE_WINDOW
        ),
        staff=window("staff", STAFF_ATTEMPTS, STAFF_WINDOW),
    )


def limiters_of(request: Request) -> Limiters:
    """Public: the login route needs the per-account delay, which no dependency can key on
    because the address it limits arrives in the body."""
    limiters: Limiters = request.app.state.limiters
    return limiters


async def _enforce(window: Allowance, key: str) -> None:
    decision = await window.check(key)
    if not decision.allowed:
        raise TooManyRequestsError(TOO_MANY, retry_after=decision.retry_after_seconds)


async def limit_login(request: Request, settings: SettingsDep) -> None:
    await _enforce(limiters_of(request).login_by_address, client_ip(request, settings))


async def limit_registration(request: Request, settings: SettingsDep) -> None:
    await _enforce(limiters_of(request).registration, client_ip(request, settings))


async def limit_reset_request(request: Request, settings: SettingsDep) -> None:
    await _enforce(limiters_of(request).reset_request, client_ip(request, settings))


async def limit_reset_confirm(request: Request, settings: SettingsDep) -> None:
    await _enforce(limiters_of(request).reset_confirm, client_ip(request, settings))


async def limit_refresh(request: Request, settings: SettingsDep) -> None:
    await _enforce(limiters_of(request).refresh, client_ip(request, settings))


async def limit_credential_change(request: Request, user: SignedInUser) -> None:
    """`SignedInUser` rather than `CurrentUser`: this guards `/auth/password`, which an
    account owing a change must still reach, and asking for the stricter one here would shut
    the door this limiter is standing next to."""
    await _enforce(limiters_of(request).credential_change, str(user.id))


async def limit_staff_actions(request: Request, admin: CurrentUser) -> None:
    await _enforce(limiters_of(request).staff, str(admin.id))


async def delay_for_account(request: Request, email: str) -> float:
    """Keyed on the address that was typed, because at this point nothing else is known —
    the account may not even exist, and the answer must not reveal which."""
    return await limiters_of(request).login_by_account.delay_for(email)


async def forget_account_delay(request: Request, email: str) -> None:
    """The guesses that came before somebody proved the account is theirs stop counting."""
    await limiters_of(request).login_by_account.forget(email)
