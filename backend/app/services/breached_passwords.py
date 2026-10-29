"""Asking whether a password has already been seen in somebody else's leak.

The useful question about a password is not how many kinds of character it contains — that
rule produces `Password1!` and a note on a monitor. It is whether this exact string is already
on a list attackers try first, and that is a question somebody else has already answered for
hundreds of millions of passwords.

**The password never leaves.** Not even hashed in full. The service is asked for every known
hash beginning with the same five hex characters — tens of thousands of them — and the match
is looked for here. Anybody watching the request learns that somebody checked a password whose
hash starts with those five characters, which is roughly nothing.

**It fails open, deliberately.** If the service is slow, down, or unreachable, the password is
accepted. A security check that can lock everybody out of registering when a third party has
an outage is a worse problem than the one it solves, and the check is advice rather than a
boundary — the thing actually protecting the account is argon2 and the rate limits.
"""

import hashlib

import httpx

from app.core.config import Settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# How many leading characters of the hash travel. Five is what the k-anonymity range API takes.
PREFIX = 5


async def is_known_leaked(settings: Settings, password: str) -> bool:
    """True only when the answer is a confident yes. Everything else is a no."""
    if not settings.breached_password_url:
        return False
    digest = hashlib.sha1(password.encode(), usedforsecurity=False).hexdigest().upper()
    prefix, suffix = digest[:PREFIX], digest[PREFIX:]
    try:
        async with httpx.AsyncClient(timeout=settings.breached_password_timeout) as client:
            response = await client.get(f"{settings.breached_password_url}/{prefix}")
            response.raise_for_status()
    except httpx.HTTPError:
        # somebody else's outage is not a reason to stop people signing up
        logger.warning("could not check the password against known leaks")
        return False
    return any(line.split(":", 1)[0] == suffix for line in response.text.splitlines())
