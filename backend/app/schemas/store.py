import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, BeforeValidator, ConfigDict, StringConstraints

from app.models import Store, StoreStatus
from app.models.store import SUBDOMAIN_MAX_LENGTH, SUBDOMAIN_MIN_LENGTH, SUBDOMAIN_PATTERN


def _normalize(value: object) -> object:
    """DNS reads a label case-insensitively, so "Cups" is not an error — it is the same address."""
    return value.strip().lower() if isinstance(value, str) else value


# BeforeValidator runs ahead of the constraints despite its position: the pattern sees the
# normalized value. StringConstraints(to_lower=...) would not — it lowercases after the pattern.
Subdomain = Annotated[
    str,
    StringConstraints(
        min_length=SUBDOMAIN_MIN_LENGTH,
        max_length=SUBDOMAIN_MAX_LENGTH,
        pattern=SUBDOMAIN_PATTERN,
    ),
    BeforeValidator(_normalize),
]


class StoreCreateRequest(BaseModel):
    subdomain: Subdomain


class StorefrontRead(BaseModel):
    """What a visitor may see. Nothing internal is listed here — not the legal name, not
    the identifiers, not the moderation status — so the public page cannot leak them."""

    subdomain: str
    display_name: str
    description: str | None
    logo_url: str | None
    banner_url: str | None
    primary_color: str | None
    secondary_color: str | None
    theme_id: str

    @classmethod
    def from_store(cls, store: Store) -> "StorefrontRead":
        return cls(
            subdomain=store.subdomain,
            display_name=store.business.display_name,
            description=store.business.description,
            logo_url=store.logo_url,
            banner_url=store.banner_url,
            primary_color=store.primary_color,
            secondary_color=store.secondary_color,
            theme_id=store.theme_id,
        )


class StoreRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    business_id: uuid.UUID
    subdomain: str
    logo_url: str | None
    banner_url: str | None
    primary_color: str | None
    secondary_color: str | None
    theme_id: str
    status: StoreStatus
    created_at: datetime
