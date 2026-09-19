import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, BeforeValidator, ConfigDict, StringConstraints

from app.models import StoreStatus
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
