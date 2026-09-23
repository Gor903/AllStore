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

    database_url: PostgresDsn
    db_echo: bool = False
    db_pool_size: int = 5

    # argon2id parameters follow the OWASP recommendation, see docs/adr/0002-password-storage.md
    argon2_time_cost: int = 2
    argon2_memory_cost: int = 19456
    argon2_parallelism: int = 1

    # token lifetimes and cookie names, see docs/adr/0001-authentication.md
    access_token_ttl_minutes: int = 15
    refresh_token_ttl_days: int = 30
    password_reset_ttl_hours: int = 2
    access_cookie_name: str = "allstore_access"
    refresh_cookie_name: str = "allstore_refresh"
    csrf_cookie_name: str = "allstore_csrf"
    csrf_header_name: str = "X-CSRF-Token"

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
    # how many times the model may search before it has to answer with what it has
    assistant_max_tool_rounds: int = 4
    # how much of the conversation travels back: enough to follow up, not to pay for a novel
    assistant_history_turns: int = 6

    @field_validator("secret_key")
    @classmethod
    def _secret_key_is_long_enough(cls, value: SecretStr) -> SecretStr:
        # HS256 signs with this key; below the hash block size the signature loses strength
        if len(value.get_secret_value()) < MIN_SECRET_KEY_LENGTH:
            raise ValueError(f"SECRET_KEY must be at least {MIN_SECRET_KEY_LENGTH} characters long")
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


@lru_cache
def get_settings() -> Settings:
    return Settings()
