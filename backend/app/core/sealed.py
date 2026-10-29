"""Short-lived state the server writes and reads back, carried by the browser.

Two things use this, and they have the same shape: a handful of values that matter for one
round trip, belong to one browser, and would be a table to expire and sweep if they lived on
our side. The Google handshake is one; the half-finished sign-in waiting for a second factor
is the other.

**Signed, because a cookie the caller can write is a cookie the caller can use to answer our
own challenge.** Unsigned, a visitor could simply write down which account they are halfway
into signing in as.

**base64url, because a cookie value may not contain the commas, quotes and braces JSON is
made of.** Left raw, the browser quotes or truncates it and the round trip is lost — which is
not a theoretical worry, it is a bug this codebase already had.

**Dated, because a signature does not expire.** A `Max-Age` is a request the browser may
decline to honour, and an attacker replaying a cookie is not using a browser at all. The
issue time travels inside the signed payload, where it cannot be edited.
"""

import base64
import hmac
import json
import time
from hashlib import sha256

from app.core.config import Settings


def seal(settings: Settings, payload: dict[str, str], *, now: float | None = None) -> str:
    stamped = {**payload, "iat": str(int(now if now is not None else time.time()))}
    body = (
        base64.urlsafe_b64encode(json.dumps(stamped, separators=(",", ":")).encode())
        .decode()
        .rstrip("=")
    )
    return f"{_signature(settings, body)}.{body}"


def unseal(
    settings: Settings, sealed: str | None, *, max_age_seconds: int, now: float | None = None
) -> dict[str, str] | None:
    """Returns what we wrote, or nothing.

    Nothing is not an error to explain. A value that fails this is somebody else's, or ours
    from another day, and either way the only useful answer is to start again.
    """
    if not sealed or "." not in sealed:
        return None
    signature, body = sealed.split(".", 1)
    if not hmac.compare_digest(signature, _signature(settings, body)):
        return None
    try:
        payload: dict[str, str] = json.loads(
            base64.urlsafe_b64decode(body + "=" * (-len(body) % 4))
        )
        issued = int(payload["iat"])
    except (json.JSONDecodeError, ValueError, KeyError):
        return None
    moment = now if now is not None else time.time()
    if moment - issued > max_age_seconds:
        return None
    return payload


def _signature(settings: Settings, body: str) -> str:
    return hmac.new(
        settings.secret_key.get_secret_value().encode(), body.encode(), sha256
    ).hexdigest()
