from functools import lru_cache
from typing import Literal

from pydantic import PostgresDsn
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Environment of the search service, validated at import time.

    The service shares the database with backend but owns exactly one table in it. Everything
    else it reads is read-only — see app/tables.py.
    """

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", case_sensitive=False
    )

    log_level: str = "INFO"
    database_url: PostgresDsn
    db_echo: bool = False

    # "fastembed" runs the real model; "fake" is deterministic and needs no download, which is
    # what CI and the tests use — an embedding model is 2 GB and proves nothing about our code
    embedder: Literal["fastembed", "fake"] = "fastembed"
    # e5 is trained for retrieval (query → document) and multilingual out of the box, so an
    # Armenian or English query finds a Russian catalogue entry without a translation step
    # (docs/rag-first.md, раздел 27). Changing this to a model of another width needs a backend
    # migration: the column type carries the width.
    embedding_model: str = "intfloat/multilingual-e5-large"
    embedding_dimensions: int = 1024

    # how many products are embedded in one pass of the model
    batch_size: int = 32
    # the sweep is the safety net under the ping from backend, not the main path
    reindex_interval_seconds: int = 300
    # how many candidates the vector search returns before the caller filters them
    default_limit: int = 20
    max_limit: int = 100


@lru_cache
def get_settings() -> Settings:
    return Settings()
