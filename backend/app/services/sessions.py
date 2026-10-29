"""Opening a session, keeping it alive, renewing it, and taking it back.

Every authorized request passes through `touch`, so the rules worth stating are here.

**One token, not two.** ADR 1 split them — a short-lived JWT so the common case cost no
database read, and a long opaque one to mint new ones. Neither half earned its keep: the
status had to be re-read on every request anyway for a block to take effect at once, so the
read was never saved; and nothing ever called the endpoint that spent the long token, so
people were signed out every fifteen minutes with a month-long credential in their jar.

**Two clocks.** The sliding one asks whether the person is still around and is pushed forward
as they use the site. The absolute one does not move: a session ends eventually however busy
it is, so a token taken from an account that is used daily does not last forever.

**Renewal is for noticing theft, not for staying signed in.** The sliding clock keeps people
signed in. Renewal exists so that a token used by two parties can be spotted: the copy that
arrives after its replacement was issued is one nobody should still be holding, and the whole
family goes. Everything inside a family is one device; a fresh sign-in starts a new one.

**The grace window is for tabs, not for thieves.** Two tabs can send a request in the same
instant; one renews, the other arrives a moment later with a token that was just retired. It
is served, because the cookie jar they share already holds the replacement. Outside that
window the same thing means what it says.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession as DbSession

from app.core import geo
from app.core.config import Settings
from app.core.errors import AccountNotActiveError, AuthenticationError
from app.core.geo import Place
from app.core.security import csrf_token_for, generate_token, hash_token
from app.models import AuthMethod, Session, User
from app.repositories import sessions as repo

# What a revocation says about itself, for the device list and for anybody reading the table.
RENEWED = "renewed"
SIGNED_OUT = "signed out"
REPLAYED = "token replayed after renewal"
CREDENTIALS_CHANGED = "credentials changed"
ACCOUNT_BLOCKED = "account blocked"
SIGNED_OUT_ELSEWHERE = "signed out from another device"


class InvalidSessionError(AuthenticationError):
    code = "invalid_session"


class SessionExpiredError(AuthenticationError):
    code = "session_expired"


@dataclass(frozen=True)
class IssuedSession:
    """What the browser has to be told. The raw token exists only here and in the cookie."""

    token: str
    csrf_token: str


@dataclass(frozen=True)
class Live:
    session: Session
    # set only when the token was renewed on this request and the cookie has to be rewritten
    renewed: IssuedSession | None = None
    # Whether this request wrote to the row, and therefore whether somebody has to commit.
    #
    # Nothing here can commit on its own — the rule is that the commit belongs to the API
    # layer — and most requests are reads that never commit anything. So every write made on
    # the way in used to be rolled back when the session closed, which was not a tidiness
    # problem: a renewal handed the browser a new token and then threw away the row it
    # belonged to, and the next request was a 401. Sessions quietly died an hour after they
    # began, for anybody whose next click happened to be a read.
    wrote: bool = False
    # Where this session has just turned up, when it is somewhere it was not before. The
    # letter belongs to the caller, after the commit — see core/geo.py for why this is almost
    # always None and why that is the ordinary case rather than a failure.
    moved_to: Place | None = None


@dataclass(frozen=True)
class Replayed:
    """A token came back after it had been retired, so every session of that device was
    revoked. Returned rather than raised because the revocation is a write and the commit
    belongs to the endpoint — the same lesson as `rotate_refresh_token` before it.

    Carries who it happened to, so the journal entry names the account rather than leaving
    an administrator to work it out from a revoked row.
    """

    user_id: uuid.UUID
    family_id: uuid.UUID


def _issued(settings: Settings, family_id: uuid.UUID, token: str) -> IssuedSession:
    return IssuedSession(token=token, csrf_token=csrf_token_for(settings, family_id))


async def open_session(
    db: DbSession,
    settings: Settings,
    user: User,
    *,
    ip: str | None = None,
    user_agent: str | None = None,
) -> IssuedSession:
    """A new device, and therefore a new family."""
    now = datetime.now(UTC)
    token = generate_token()
    family_id = uuid.uuid4()
    # where it began, so that a later request from somewhere else is a comparison rather than
    # a first sighting. Blank when nothing can say, which is the ordinary case.
    began = geo.locate(ip)
    await repo.add(
        db,
        Session(
            user_id=user.id,
            family_id=family_id,
            token_hash=hash_token(token),
            user_agent=user_agent[:255] if user_agent else None,
            ip=ip,
            country=began.country,
            asn=began.asn,
            auth_method=AuthMethod.PASSWORD,
            idle_expires_at=now + timedelta(days=settings.session_idle_ttl_days),
            absolute_expires_at=now + timedelta(days=settings.session_absolute_ttl_days),
        ),
    )
    return _issued(settings, family_id, token)


async def touch(
    db: DbSession, settings: Settings, raw_token: str, *, ip: str | None = None
) -> Live | Replayed:
    """The per-request path: is this session alive, and does its token need renewing.

    A session bound to a device key is never renewed from here. Renewal is the moment that
    binding exists to protect, and only the client can sign for it — so a bound session is
    renewed when it asks, at `/auth/renew`, carrying a proof.
    """
    row = await repo.get_by_hash(db, hash_token(raw_token))
    if row is None:
        raise InvalidSessionError("Сессия недействительна, войдите заново")
    now = datetime.now(UTC)

    if row.revoked_at is not None:
        return await _answer_for_a_retired_token(db, settings, row, now)

    if row.absolute_expires_at <= now or row.idle_expires_at <= now:
        raise SessionExpiredError("Сессия истекла, войдите заново")

    wrote = _slide(row, settings, now, ip)
    recorded, moved_to = _notice_a_move(row, settings, ip, now)
    wrote = wrote or recorded
    if _is_due_for_renewal(row, settings, now) and row.device_public_key is None:
        return Live(
            session=row,
            renewed=await renew(db, settings, row),
            wrote=True,
            moved_to=moved_to,
        )
    await db.flush()
    return Live(session=row, wrote=wrote, moved_to=moved_to)


def _notice_a_move(
    row: Session, settings: Settings, ip: str | None, now: datetime
) -> tuple[bool, Place | None]:
    """Whether the row was written to, and where this session has turned up if it has moved.

    Two answers because they are different questions. The place is recorded whenever anybody
    can name it, so a session that began before a source existed gets filled in on its next
    request — and that first filling-in is not a move, because there is nothing to have moved
    from. It is still a write, and a write nobody commits is a write that happens again on
    every request afterwards.

    The claim that this is the same person is withdrawn when it is: `verified_at` is pushed
    back just past the step-up window, which is the same as saying the password was proved too
    long ago. Not a sign-out — people do travel, and ending the session of everybody who
    boards a plane is a worse platform than one that asks for a password at the gate.
    """
    here = geo.locate(ip)
    if not here.known:
        return False, None
    before = Place(country=row.country, asn=row.asn)
    if (before.country, before.asn) == (here.country, here.asn):
        return False, None
    row.country, row.asn = here.country, here.asn
    if not geo.moved(before, here):
        return True, None
    row.verified_at = now - timedelta(minutes=settings.step_up_ttl_minutes + 1)
    return True, here


def _is_due_for_renewal(row: Session, settings: Settings, now: datetime) -> bool:
    return now - row.created_at >= timedelta(minutes=settings.session_renew_after_minutes)


async def _answer_for_a_retired_token(
    db: DbSession, settings: Settings, row: Session, now: datetime
) -> Live | Replayed:
    """Why a token was retired decides what its reappearance means.

    Only one reason makes a returning token evidence of anything: it was swapped for a
    successor, so somebody is still holding a copy that should have been forgotten. A token
    retired because the person signed out, or because the password changed, or because the
    account was barred is simply a token that stopped working — treating that as a theft
    would revoke a family that is already revoked and, worse, would tell the honest owner
    their device had been compromised because they pressed "sign out" twice.
    """
    if row.revoked_reason == ACCOUNT_BLOCKED:
        # the account's own state is the more useful answer, and the one it used to give
        # before barring somebody also took their sessions away
        raise AccountNotActiveError("Доступ к аккаунту ограничен, обратитесь в поддержку")
    retired_at = row.revoked_at
    if row.revoked_reason != RENEWED or retired_at is None:
        raise InvalidSessionError("Сессия недействительна, войдите заново")
    if row.replaced_by_id is not None and now - retired_at <= _grace(settings):
        # a tab that was a moment late; the jar it shares already holds the replacement
        return Live(session=row)
    await repo.revoke_family(db, row.family_id, REPLAYED)
    return Replayed(user_id=row.user_id, family_id=row.family_id)


async def peek(db: DbSession, settings: Settings, raw_token: str) -> Session | None:
    """Is this session alive — asked by a route that will not be writing anything.

    Deliberately inert. The public catalogue reads the viewer so that a shop which barred them
    can hide itself, and that page is the wrong place to discover a theft and a worse place to
    act on one: the reader would be signed out mid-scroll by a request they did not make, and
    the revocation would ride on a route that never commits and so would be lost anyway.
    """
    row = await repo.get_by_hash(db, hash_token(raw_token))
    if row is None or row.revoked_at is not None:
        return None
    now = datetime.now(UTC)
    if row.absolute_expires_at <= now or row.idle_expires_at <= now:
        return None
    return row


def _slide(row: Session, settings: Settings, now: datetime, ip: str | None) -> bool:
    """Pushes the idle clock forward — but not on every single request. Says whether it did.

    Writing a row for every image a page loads would turn a read-mostly table into a
    write-mostly one for no gain: a session that was alive a few seconds ago is alive. The
    same throttle is what keeps the commit this now implies down to one a minute per session.
    """
    if now - row.last_seen_at < timedelta(seconds=settings.session_touch_interval_seconds):
        return False
    row.last_seen_at = now
    row.idle_expires_at = now + timedelta(days=settings.session_idle_ttl_days)
    if ip is not None:
        row.ip = ip
    return True


async def renew(db: DbSession, settings: Settings, row: Session) -> IssuedSession:
    """A new row in the same family, and the old one retired pointing at it.

    A new row rather than a new value in this one, because `replaced_by_id` is what tells a
    replayed token apart from a token nobody was ever given.
    """
    token = generate_token()
    successor = await repo.add(
        db,
        Session(
            user_id=row.user_id,
            family_id=row.family_id,
            token_hash=hash_token(token),
            device_public_key=row.device_public_key,
            user_agent=row.user_agent,
            ip=row.ip,
            country=row.country,
            asn=row.asn,
            auth_method=row.auth_method,
            # Carried, and this is not bookkeeping: the successor is the row the next proof
            # will be checked against, and a fresh row with no memory would accept the
            # signature that just created it. The replay protection lives in the family, not
            # in whichever row happens to be current.
            last_proof_at=row.last_proof_at,
            idle_expires_at=row.idle_expires_at,
            # deliberately inherited: renewing must not push the end of the session away,
            # or the absolute clock would be no clock at all
            absolute_expires_at=row.absolute_expires_at,
            verified_at=row.verified_at,
        ),
    )
    await repo.revoke(db, row, RENEWED, replaced_by_id=successor.id)
    return _issued(settings, row.family_id, token)


def _grace(settings: Settings) -> timedelta:
    return timedelta(seconds=settings.session_grace_seconds)


async def sign_out(db: DbSession, row: Session) -> None:
    """This device only. The others are somebody's phone and are none of this request's
    business — see `sign_out_everywhere` for the one that is."""
    await repo.revoke_family(db, row.family_id, SIGNED_OUT)


async def sign_out_everywhere(db: DbSession, user_id: uuid.UUID, reason: str) -> None:
    await repo.revoke_all_for_user(db, user_id, reason)


async def extend_for_a_bound_device(db: DbSession, settings: Settings, row: Session) -> None:
    """A device that can prove it is still itself is worth trusting for longer.

    The roadmap framed this the other way round — a shorter life for browsers that cannot
    hold a key — and it comes to the same clock. Framed as a reward it does not read as a
    punishment for using an old browser, which is not the message anybody intended to send.
    """
    row.absolute_expires_at = row.created_at + timedelta(
        days=settings.session_bound_absolute_ttl_days
    )
    await db.flush()


async def mark_verified(db: DbSession, row: Session) -> None:
    """The person just proved the password again, which buys them a few minutes of being
    allowed to do the things that ask for it."""
    row.verified_at = datetime.now(UTC)
    await db.flush()


def is_freshly_verified(row: Session, settings: Settings) -> bool:
    age = datetime.now(UTC) - row.verified_at
    return age <= timedelta(minutes=settings.step_up_ttl_minutes)
