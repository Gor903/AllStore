"""One-time codes from an authenticator application, as RFC 6238 defines them.

Written out rather than taken from a library because there is barely anything to it: a
counter of thirty-second steps, an HMAC over that counter, and six digits read out of the
result. The whole algorithm is the two functions below, and a dependency for it would be a
dependency to audit, update and explain.

SHA-1 and six digits and thirty seconds are not choices — they are what every authenticator
application assumes when the `otpauth://` link does not say otherwise, and saying otherwise
means codes that Google Authenticator quietly computes differently from ours.
"""

import base64
import hashlib
import hmac
import secrets
import struct
from urllib.parse import quote

# What an authenticator shows: six digits, replaced every thirty seconds.
DIGITS = 6
STEP_SECONDS = 30
# How many steps either side of now are accepted. One covers the ordinary case — a phone
# whose clock is a little out, or somebody typing the last digit as the code turns over —
# and widening it would widen the guessing window by the same amount.
DRIFT_STEPS = 1
# 20 bytes, the size of the SHA-1 block the code is read out of. More would be discarded.
SECRET_BYTES = 20


def generate_secret() -> str:
    """A new shared secret, in the base32 an authenticator can be given."""
    return base64.b32encode(secrets.token_bytes(SECRET_BYTES)).decode().rstrip("=")


def step_at(moment: float) -> int:
    """Which thirty-second step a point in time falls in."""
    return int(moment // STEP_SECONDS)


def code_for(secret: str, step: int) -> str:
    """The six digits this secret produces for that step."""
    key = base64.b32decode(secret + "=" * (-len(secret) % 8), casefold=True)
    digest = hmac.new(key, struct.pack(">Q", step), hashlib.sha1).digest()
    # the last nibble says where in the digest the number starts — "dynamic truncation",
    # so that an attacker cannot know in advance which bytes of the HMAC they are attacking
    offset = digest[-1] & 0x0F
    (chunk,) = struct.unpack(">I", digest[offset : offset + 4])
    return str((chunk & 0x7FFF_FFFF) % 10**DIGITS).zfill(DIGITS)


def matching_step(secret: str, code: str, moment: float, *, after: int | None = None) -> int | None:
    """Which step this code belongs to, or nothing.

    Returns the step rather than a yes, because the caller has to remember it: the same code
    is valid for a whole step and for the drift either side of it, so without recording which
    one was used, a code read over somebody's shoulder works a second time.

    `after` is that memory — the last step this account used. Anything at or before it is
    refused however well it computes.
    """
    typed = code.strip().replace(" ", "")
    if not typed.isdigit() or len(typed) != DIGITS:
        return None
    now = step_at(moment)
    for step in range(now - DRIFT_STEPS, now + DRIFT_STEPS + 1):
        if after is not None and step <= after:
            continue
        # compare_digest: the comparison itself must not say how many leading digits were right
        if hmac.compare_digest(code_for(secret, step), typed):
            return step
    return None


def provisioning_uri(secret: str, account: str, issuer: str) -> str:
    """The `otpauth://` link an authenticator reads from a QR code.

    The issuer appears twice on purpose — once in the label and once as a parameter. Older
    applications read only the label, newer ones only the parameter, and an entry showing
    nothing but an email address is one nobody can tell from their other six.
    """
    label = quote(f"{issuer}:{account}")
    query = "&".join(
        [
            f"secret={secret}",
            f"issuer={quote(issuer)}",
            "algorithm=SHA1",
            f"digits={DIGITS}",
            f"period={STEP_SECONDS}",
        ]
    )
    return f"otpauth://totp/{label}?{query}"
