from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, PostgresDsn, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


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

    database_url: PostgresDsn
    db_echo: bool = False
    db_pool_size: int = 5

    # argon2id parameters follow the OWASP recommendation, see docs/adr/0002-password-storage.md
    argon2_time_cost: int = 2
    argon2_memory_cost: int = 19456
    argon2_parallelism: int = 1

    s3_endpoint_url: str
    s3_region: str = "us-east-1"
    s3_access_key: str
    s3_secret_key: SecretStr
    s3_bucket: str
    s3_public_url: str | None = None
    max_upload_size_mb: int = 5

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        if isinstance(value, str) and not value.startswith("["):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @property
    def is_local(self) -> bool:
        return self.app_env == "local"


@lru_cache
def get_settings() -> Settings:
    return Settings()
