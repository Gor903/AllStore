import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, BeforeValidator, ConfigDict, StringConstraints, model_validator

from app.models import Business, Store, StoreStatus
from app.models.store import (
    AVAILABLE_THEMES,
    COLOUR_PATTERN,
    SUBDOMAIN_MAX_LENGTH,
    SUBDOMAIN_MIN_LENGTH,
    SUBDOMAIN_PATTERN,
)
from app.schemas.contact import ContactRead

# a shop tells its story, it does not write an article
DESCRIPTION_MAX_LENGTH = 2000


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


def _normalize_colour(value: object) -> object:
    """#AABBCC and #aabbcc are the same colour, and the column keeps one shape."""
    return value.strip().lower() if isinstance(value, str) else value


Colour = Annotated[
    str,
    StringConstraints(pattern=COLOUR_PATTERN),
    BeforeValidator(_normalize_colour),
]
StoreDescription = Annotated[
    str, StringConstraints(strip_whitespace=True, max_length=DESCRIPTION_MAX_LENGTH)
]

# everything a seller may clear back to the default look; the subdomain is not among them
CLEARABLE_FIELDS = frozenset({"description", "primary_color", "secondary_color"})


class StoreUpdateRequest(BaseModel):
    """Only the fields present in the body change. Null clears a field back to the default,
    which for a colour means the theme decides and for a description means none is shown.

    The subdomain is not here: it is the address the seller has already given out, and the
    storefront answers at it. Renaming it is a separate decision with its own redirects.
    """

    model_config = ConfigDict(extra="forbid")

    description: StoreDescription | None = None
    primary_color: Colour | None = None
    secondary_color: Colour | None = None
    theme_id: str | None = None

    @model_validator(mode="after")
    def _check(self) -> "StoreUpdateRequest":
        nulled = sorted(
            field
            for field in self.model_fields_set
            if getattr(self, field) is None and field not in CLEARABLE_FIELDS
        )
        if nulled:
            raise ValueError(f"Эти поля нельзя очистить: {', '.join(nulled)}")
        if self.theme_id is not None and self.theme_id not in AVAILABLE_THEMES:
            raise ValueError(f"Неизвестная тема, доступны: {', '.join(sorted(AVAILABLE_THEMES))}")
        return self


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
    contacts: list[ContactRead]

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
            contacts=[ContactRead.from_link(link) for link in store.business.social_links],
        )


class StoreRead(BaseModel):
    """What the seller sees of their own storefront. The description is kept on the
    business, so it is passed in rather than read through a relation that may not be
    loaded — a lazy load in the async session would have nowhere to run."""

    id: uuid.UUID
    business_id: uuid.UUID
    subdomain: str
    description: str | None
    logo_url: str | None
    banner_url: str | None
    primary_color: str | None
    secondary_color: str | None
    theme_id: str
    status: StoreStatus
    created_at: datetime

    @classmethod
    def of(cls, store: Store, business: Business) -> "StoreRead":
        return cls(
            id=store.id,
            business_id=store.business_id,
            subdomain=store.subdomain,
            description=business.description,
            logo_url=store.logo_url,
            banner_url=store.banner_url,
            primary_color=store.primary_color,
            secondary_color=store.secondary_color,
            theme_id=store.theme_id,
            status=store.status,
            created_at=store.created_at,
        )
