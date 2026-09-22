import enum
import uuid

from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import storage
from app.core.config import Settings
from app.core.errors import NotFoundError
from app.core.images import SUPPORTED_CONTENT_TYPES, detect_image_format
from app.models import Business, Store
from app.repositories import stores
from app.schemas.store import StoreUpdateRequest
from app.services.product_images import BYTES_IN_MB, UnsupportedImageError, read_within_limit


class StoreImageKind(enum.StrEnum):
    LOGO = "logo"
    BANNER = "banner"


# the column each kind writes to, so the two differ in one place and not in two routes
_COLUMN = {StoreImageKind.LOGO: "logo_url", StoreImageKind.BANNER: "banner_url"}


class StoreNotFoundError(NotFoundError):
    code = "store_not_found"


async def get_own_store(session: AsyncSession, business_id: uuid.UUID) -> Store:
    store = await stores.get_by_business(session, business_id)
    if store is None:
        raise StoreNotFoundError("У аккаунта нет витрины")
    return store


async def update_store(
    session: AsyncSession, business: Business, payload: StoreUpdateRequest
) -> Store:
    """Description lives on the business and the look on the storefront, but the seller
    edits one thing — their shop — so one request covers both."""
    store = await get_own_store(session, business.id)
    changes = payload.model_dump(exclude_unset=True)
    if "description" in changes:
        business.description = changes.pop("description")
    for field, value in changes.items():
        setattr(store, field, value)

    await session.flush()
    # updated_at is computed by the database on UPDATE, so the column comes back expired
    await session.refresh(store, attribute_names=["updated_at"])
    return store


async def set_image(
    session: AsyncSession,
    settings: Settings,
    business_id: uuid.UUID,
    kind: StoreImageKind,
    upload: UploadFile,
) -> tuple[Store, str | None]:
    """Replaces the logo or the banner. Answers with the key of the object it displaced,
    for the caller to drop once the new address is committed."""
    store = await get_own_store(session, business_id)
    data = await read_within_limit(upload, settings.max_upload_size_mb * BYTES_IN_MB)
    image_format = detect_image_format(data)
    if image_format is None:
        raise UnsupportedImageError(
            f"Загрузить можно только изображение: {', '.join(SUPPORTED_CONTENT_TYPES)}",
            details=[{"loc": ["body", "file"], "msg": "Это не изображение"}],
        )

    # the tenant owns its prefix, so a key cannot be confused with another business's
    key = f"stores/{business_id}/{kind}/{uuid.uuid4().hex}{image_format.extension}"
    displaced = storage.key_from_url(settings, getattr(store, _COLUMN[kind]) or "")
    # the row goes in before the upload: a failed upload rolls the transaction back and
    # leaves nothing behind, while the reverse order would strand an object in the bucket
    setattr(store, _COLUMN[kind], storage.public_url(settings, key))
    await session.flush()
    await storage.put_object(settings, key, data, image_format.content_type)
    return store, displaced


async def clear_image(
    session: AsyncSession, settings: Settings, business_id: uuid.UUID, kind: StoreImageKind
) -> tuple[Store, str | None]:
    store = await get_own_store(session, business_id)
    displaced = storage.key_from_url(settings, getattr(store, _COLUMN[kind]) or "")
    setattr(store, _COLUMN[kind], None)
    await session.flush()
    return store, displaced
