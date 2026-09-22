"""The catalogue's reference book, and the only place it changes.

Until now categories arrived by migration: adding one meant a deploy. They are edited here
instead, with the two rules the catalogue depends on kept in the service rather than in the
routes — the tree stays two levels deep, and a slug stays unique because it is the address
a visitor filters by.

Nothing is deleted. Hiding keeps a category out of the catalogue while the products filed
under it stay where they are; deleting would take the products with it.
"""

import uuid
from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, NotFoundError, ValidationFailedError
from app.models import Category, CategoryStatus, User
from app.repositories import categories as categories_repo
from app.services import audit

ENTITY = "category"


class CategoryNotFoundError(NotFoundError):
    code = "category_not_found"


class SlugTakenError(ConflictError):
    code = "category_slug_taken"


class TreeTooDeepError(ValidationFailedError):
    code = "category_tree_too_deep"


async def list_tree(session: AsyncSession) -> Sequence[Category]:
    return await categories_repo.list_tree(session)


async def create(
    session: AsyncSession,
    admin: User,
    name: str,
    slug: str,
    parent_id: uuid.UUID | None,
) -> Category:
    await _refuse_taken_slug(session, slug)
    if parent_id is not None:
        parent = await find(session, parent_id)
        if parent.parent_id is not None:
            raise TreeTooDeepError(
                "Каталог двухуровневый: подкатегорию нельзя вложить в подкатегорию"
            )

    category = await categories_repo.add(
        session, Category(name=name, slug=slug, parent_id=parent_id)
    )
    await audit.record(
        session, admin, "category.created", ENTITY, category.id, name=name, slug=slug
    )
    return category


async def rename(session: AsyncSession, admin: User, category_id: uuid.UUID, name: str) -> Category:
    category = await find(session, category_id)
    if category.name == name:
        return category

    previous = category.name
    category.name = name
    await session.flush()
    await audit.record(
        session, admin, "category.renamed", ENTITY, category.id, **{"from": previous, "to": name}
    )
    return category


async def set_status(
    session: AsyncSession, admin: User, category_id: uuid.UUID, status: CategoryStatus
) -> Category:
    category = await find(session, category_id)
    if category.status is status:
        return category

    category.status = status
    await session.flush()
    action = "category.hidden" if status is CategoryStatus.HIDDEN else "category.shown"
    await audit.record(session, admin, action, ENTITY, category.id, name=category.name)
    return category


async def find(session: AsyncSession, category_id: uuid.UUID) -> Category:
    category = await categories_repo.get_by_id(session, category_id)
    if category is None:
        raise CategoryNotFoundError("Категория не найдена")
    return category


async def _refuse_taken_slug(session: AsyncSession, slug: str) -> None:
    if await categories_repo.get_by_slug(session, slug) is not None:
        raise SlugTakenError(
            "Этот адрес категории уже занят",
            details=[{"loc": ["body", "slug"], "msg": "Адрес занят"}],
        )
