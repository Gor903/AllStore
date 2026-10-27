import uuid
from datetime import datetime
from typing import Annotated, Any

from pydantic import BaseModel, BeforeValidator, ConfigDict, StringConstraints

from app.models import AuditLog, Category, CategoryStatus, UserRole
from app.models.category import CATEGORY_SLUG_MAX_LENGTH, CATEGORY_SLUG_PATTERN
from app.schemas.auth import UserRead


class UserListResponse(BaseModel):
    items: list[UserRead]
    total: int
    limit: int
    offset: int


class RoleChangeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: UserRole


class AuditLogRead(BaseModel):
    id: uuid.UUID
    action: str
    entity_type: str
    entity_id: uuid.UUID | None
    details: dict[str, Any]
    created_at: datetime
    # the email rather than the identifier: a journal is read by people
    actor_email: str | None

    @classmethod
    def from_entry(cls, entry: AuditLog) -> "AuditLogRead":
        return cls(
            id=entry.id,
            action=entry.action,
            entity_type=entry.entity_type,
            entity_id=entry.entity_id,
            details=entry.details,
            created_at=entry.created_at,
            actor_email=None if entry.actor is None else entry.actor.email,
        )


class AuditLogListResponse(BaseModel):
    items: list[AuditLogRead]
    total: int
    limit: int
    offset: int


CategoryName = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)
]


def _normalize_slug(value: object) -> object:
    """Lowercased before the pattern sees it. StringConstraints(to_lower=...) would not:
    it lowercases after the pattern, so PETS would be refused rather than accepted as pets
    — the same trap the subdomain hit, see app/schemas/store.py."""
    return value.strip().lower() if isinstance(value, str) else value


CategorySlug = Annotated[
    str,
    StringConstraints(
        min_length=1,
        max_length=CATEGORY_SLUG_MAX_LENGTH,
        pattern=CATEGORY_SLUG_PATTERN,
    ),
    BeforeValidator(_normalize_slug),
]


class CategoryCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: CategoryName
    slug: CategorySlug
    # null makes a top-level category; the catalogue tree is two levels deep
    parent_id: uuid.UUID | None = None


class CategoryUpdateRequest(BaseModel):
    """Only what is present changes. The slug is absent on purpose: it is the address a
    visitor filters by and a link they may have saved, so renaming it is not an edit."""

    model_config = ConfigDict(extra="forbid")

    name: CategoryName | None = None
    status: CategoryStatus | None = None


class AdminCategoryRead(BaseModel):
    """Unlike the public tree this one carries the status: an administrator manages what a
    visitor must not see just as much as what they may."""

    id: uuid.UUID
    name: str
    slug: str
    status: CategoryStatus
    children: list["AdminCategoryRead"]

    @classmethod
    def leaf(cls, category: Category) -> "AdminCategoryRead":
        return cls(
            id=category.id,
            name=category.name,
            slug=category.slug,
            status=category.status,
            children=[],
        )

    @classmethod
    def from_root(cls, category: Category) -> "AdminCategoryRead":
        return cls(
            id=category.id,
            name=category.name,
            slug=category.slug,
            status=category.status,
            children=[cls.leaf(child) for child in category.children],
        )
