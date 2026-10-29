from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, PostgresDsn, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

MIN_SECRET_KEY_LENGTH = 32

# names that must keep resolving to us, not to a storefront: infrastructure hosts, our own
# routes, and the addresses mail and TLS tooling expects. Override per environment.
DEFAULT_RESERVED_SUBDOMAINS = (
    "admin",
    "api",
    "app",
    "assets",
    "auth",
    "blog",
    "cdn",
    "dashboard",
    "dev",
    "docs",
    "ftp",
    "help",
    "imap",
    "internal",
    "mail",
    "mx",
    "ns1",
    "ns2",
    "shop",
    "smtp",
    "staging",
    "static",
    "status",
    "store",
    "support",
    "test",
    "www",
)


class Settings(BaseSettings):
    """Environment configuration, validated at import time — see infra/env/backend.env.example."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_env: Literal["local", "staging", "production"] = "local"
    log_level: str = "INFO"
    api_prefix: str = "/api/v1"
    secret_key: SecretStr
    base_domain: str = "allstore.am"
    # NoDecode: keep the raw env string so the validator below can accept a comma-separated list
    cors_origins: Annotated[list[str], NoDecode] = Field(default_factory=list)
    reserved_subdomains: Annotated[frozenset[str], NoDecode] = frozenset(
        DEFAULT_RESERVED_SUBDOMAINS
    )
    # Addresses and networks whose `X-Forwarded-For` the platform believes — see
    # core/client_ip.py. Empty means believe nobody, which is right when nothing stands in
    # front; behind a proxy it must name the proxy, or every visitor shares one allowance.
    trusted_proxies: Annotated[tuple[str, ...], NoDecode] = ()

    database_url: PostgresDsn
    db_echo: bool = False
    db_pool_size: int = 5

    # argon2id parameters follow the OWASP recommendation, see docs/adr/0002-password-storage.md
    argon2_time_cost: int = 2
    argon2_memory_cost: int = 19456
    argon2_parallelism: int = 1
    # how many passwords may be hashed at once, each costing argon2_memory_cost — see
    # core/security.py. Four is ~76 MiB at the default memory cost
    argon2_max_parallel: int = 4
    # Whether a chosen password is already on a list attackers try first — see
    # services/breached_passwords.py. The password never leaves: only five characters of its
    # hash do. Empty disables the check, which is what the suite does.
    breached_password_url: str | None = "https://api.pwnedpasswords.com/range"  # noqa: S105
    # a check that takes longer than this is worse than no check: somebody is waiting
    breached_password_timeout: float = 3.0

    # Session lifetimes and cookie names, see docs/adr/0018-server-side-sessions.md, which
    # revises ADR 1. Two clocks: the sliding one asks whether the person is still around, the
    # absolute one ends a session however busy it is.
    session_idle_ttl_days: int = 30
    session_absolute_ttl_days: int = 90
    # A session that can prove it is still the same device — see services/device_keys.py —
    # is worth trusting for longer than one that can only produce a cookie.
    session_bound_absolute_ttl_days: int = 180
    # how old a token may get before it is swapped for a fresh one in the same family. This
    # is what makes a stolen copy detectable, not what keeps anybody signed in.
    session_renew_after_minutes: int = 60
    # a token retired this recently is still served: two tabs can race, and they share a jar
    session_grace_seconds: int = 30
    # the sliding clock is not pushed more often than this, so a page of images is one write
    session_touch_interval_seconds: int = 60
    # how long proving the password again buys, for the actions that ask for it twice
    step_up_ttl_minutes: int = 10
    password_reset_ttl_hours: int = 2
    # longer than a reset link: confirming an address is not urgent, and a link that expires
    # while somebody is away from their inbox just means another round of letters
    email_verification_ttl_hours: int = 24
    session_cookie_name: str = "allstore_session"
    csrf_cookie_name: str = "allstore_csrf"
    csrf_header_name: str = "X-CSRF-Token"
    # Where a request is allowed to have come from for a mutating call to be served. Empty
    # falls back to the site's own address — see deps/auth.require_csrf.
    allowed_origins: Annotated[tuple[str, ...], NoDecode] = ()

    # Mail. Unset SMTP_HOST means no transport: the local stand logs its letters and the
    # suite needs no mail server. See docs/adr/0019-transactional-mail.md — this is a stopgap
    # on a personal account, and the whole point of keeping it to four settings is that
    # moving to a hosted provider is a change of four settings.
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: SecretStr | None = None
    smtp_starttls: bool = True
    smtp_timeout: float = 20.0
    # Gmail rewrites this to the account that authenticated, so on a personal account it has
    # to be that address. A hosted provider lets it be anything on a verified domain.
    mail_from: str = "noreply@allstore.am"
    mail_from_name: str = "AllStore.am"
    # where a link in a letter points; the backend has no other way to know its own address
    site_url: str | None = None

    # the first administrator, read once by scripts/bootstrap_admin.py and never again: after
    # that the database is the authority on who administers the platform, not the environment
    admin_email: str | None = None
    admin_password: SecretStr | None = None

    s3_endpoint_url: str
    s3_region: str = "us-east-1"
    s3_access_key: str
    s3_secret_key: SecretStr
    s3_bucket: str
    s3_public_url: str | None = None
    max_upload_size_mb: int = 5

    # the semantic search service, see docs/rag-first.md. Unset means the catalogue searches
    # exactly as it always did — the site does not depend on it being there (ADR 10)
    search_service_url: str | None = None
    # a search that takes longer than this is worse than no search: the visitor is waiting
    search_timeout_seconds: float = 2.0
    # how many suggestions the semantic side contributes.
    #
    # Deliberately small and fixed. A vector search ranks, it does not match: it always
    # returns something, and the scores fall off so gently that any threshold would be a
    # magic number that drifts with the model. A large pool would inflate the number of
    # found products with things nobody was looking for, so the semantic side adds a short
    # list of best guesses — every one of them marked as such in the answer.
    search_candidates: int = 20

    # the assistant (docs/rag-first.md, раздел 26). Any OpenAI-compatible endpoint with tool
    # calling: a local Ollama on the stand, a hosted provider later — the backend speaks the
    # protocol, not a vendor SDK. Unset means the assistant is simply not offered.
    assistant_base_url: str | None = None
    assistant_model: str = "qwen2.5:3b"
    # only hosted endpoints need it; a local model has no key at all
    assistant_api_key: SecretStr | None = None
    # a small model on a CPU is slow, and the visitor is told to wait rather than lied to
    assistant_timeout_seconds: float = 120.0
    assistant_max_tokens: int = 700
    # low, not zero: at the default a small model sometimes skips the search and answers from
    # nothing, and a shop assistant that invents is worse than one that repeats itself
    assistant_temperature: float = 0.2
    # how many times the model may search before it has to answer with what it has
    assistant_max_tool_rounds: int = 4
    # how much of the conversation travels back: enough to follow up, not to pay for a novel
    assistant_history_turns: int = 6

    @field_validator(
        "search_service_url",
        "assistant_base_url",
        "s3_public_url",
        "smtp_host",
        "breached_password_url",
        mode="before",
    )
    @classmethod
    def _blank_means_unset(cls, value: object) -> object:
        """An empty variable is how an env file says "off".

        `SEARCH_SERVICE_URL=` in a file and an absent SEARCH_SERVICE_URL mean the same thing
        to whoever wrote it, and both have to mean the same thing here — otherwise the
        catalogue tries to call an empty address on every search.
        """
        return None if isinstance(value, str) and not value.strip() else value

    @field_validator("secret_key")
    @classmethod
    def _secret_key_is_long_enough(cls, value: SecretStr) -> SecretStr:
        # HS256 signs with this key; below the hash block size the signature loses strength
        if len(value.get_secret_value()) < MIN_SECRET_KEY_LENGTH:
            raise ValueError(f"SECRET_KEY must be at least {MIN_SECRET_KEY_LENGTH} characters long")
        return value

    @field_validator("trusted_proxies", "allowed_origins", mode="before")
    @classmethod
    def _split_comma_separated(cls, value: object) -> object:
        if isinstance(value, str):
            return tuple(item.strip() for item in value.split(",") if item.strip())
        return value

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        if isinstance(value, str) and not value.startswith("["):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @field_validator("reserved_subdomains", mode="before")
    @classmethod
    def _split_reserved_subdomains(cls, value: object) -> object:
        # compared against an already lowercased subdomain, so the env value is lowered too
        if isinstance(value, str):
            names = {item.strip().lower() for item in value.split(",") if item.strip()}
            # an unset variable reaches us as an empty string — it must not free every name
            return names or frozenset(DEFAULT_RESERVED_SUBDOMAINS)
        return value

    @property
    def is_local(self) -> bool:
        return self.app_env == "local"

    @property
    def session_cookie(self) -> str:
        """The name the browser actually sees.

        `__Host-` is not decoration. A browser refuses to store a cookie under that prefix
        unless it is `Secure`, carries no `Domain` and sits at `Path=/` — so host-only stops
        being a promise we make and becomes a rule the client enforces. It also means no
        subdomain can overwrite it, which is the whole of the cookie-tossing problem.

        Every cookie here can wear it now that there is one session token instead of a pair:
        the old refresh token had to settle for `__Secure-`, because it was scoped to the auth
        routes and `__Host-` demands `Path=/`.

        The prefix needs `Secure`, which the plain-http local stand cannot offer, so there the
        bare name is used. Both names must match the frontend's NEXT_PUBLIC_SESSION_COOKIE.
        """
        return self.session_cookie_name if self.is_local else f"__Host-{self.session_cookie_name}"

    @property
    def csrf_cookie(self) -> str:
        """`__Host-` like the access cookie: it is host-only and at the root already, and the
        prefix is what stops a neighbouring subdomain from planting its own value here and
        satisfying the double submit with it."""
        return self.csrf_cookie_name if self.is_local else f"__Host-{self.csrf_cookie_name}"

    @property
    def public_url(self) -> str:
        """What a link in a letter has to say. Falls back to the domain we already know."""
        return self.site_url or f"https://{self.base_domain}"

    @property
    def trusted_origins(self) -> tuple[str, ...]:
        """Where a mutating request may have come from.

        Falls back to the CORS list rather than inventing an address: those are already the
        origins a browser is allowed to call us from, and keeping two lists that mean almost
        the same thing is how they come to disagree. Empty means the check has nothing to
        compare against and stands down — the CSRF token still has to match.
        """
        return self.allowed_origins or tuple(self.cors_origins)


@lru_cache
def get_settings() -> Settings:
    return Settings()
