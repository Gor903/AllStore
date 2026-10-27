from fastapi import Request

from app.core.errors import TooManyRequestsError
from app.core.rate_limit import SlidingWindow

# an invited person needs one attempt and perhaps a second one after a typo; ten in five
# minutes from one address is nobody filling in a form
INVITATION_ATTEMPT_LIMIT = 10
INVITATION_ATTEMPT_WINDOW_SECONDS = 300.0


def build_invitation_limiter() -> SlidingWindow:
    """One per application rather than one per module, so each process keeps its own tally
    and a test gets a fresh one with its app instead of inheriting the previous test's."""
    return SlidingWindow(INVITATION_ATTEMPT_LIMIT, INVITATION_ATTEMPT_WINDOW_SECONDS)


def limit_invitation_attempts(request: Request) -> None:
    limiter: SlidingWindow = request.app.state.invitation_limiter
    # the address, not the token: keying on what was submitted would give every guess its
    # own allowance, which is the opposite of a limit
    caller = "unknown" if request.client is None else request.client.host
    if not limiter.allow(caller):
        raise TooManyRequestsError("Слишком много попыток, попробуйте позже")
