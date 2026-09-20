import uuid

from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import storage
from app.core.config import Settings
from app.core.errors import (
    ConflictError,
    NotFoundError,
    PayloadTooLargeError,
    ValidationFailedError,
)
from app.core.images import SUPPORTED_CONTENT_TYPES, detect_image_format
from app.models import ProductImage
from app.repositories import product_images
from app.services import products as products_service

BYTES_IN_MB = 1024 * 1024
# enough for a gallery, low enough that one product cannot fill the bucket
MAX_IMAGES_PER_PRODUCT = 10


class UnsupportedImageError(ValidationFailedError):
    code = "unsupported_image_type"


class ImageTooLargeError(PayloadTooLargeError):
    code = "image_too_large"


class ImageLimitReachedError(ConflictError):
    code = "image_limit_reached"


class ImageNotFoundError(NotFoundError):
    code = "image_not_found"


async def add_image(
    session: AsyncSession,
    settings: Settings,
    business_id: uuid.UUID,
    product_id: uuid.UUID,
    upload: UploadFile,
    alt_text: str | None,
) -> ProductImage:
    product = await products_service.get_owned_product(session, business_id, product_id)
    if await product_images.count_for_product(session, product.id) >= MAX_IMAGES_PER_PRODUCT:
        raise ImageLimitReachedError(f"У товара не может быть больше {MAX_IMAGES_PER_PRODUCT} фото")

    data = await read_within_limit(upload, settings.max_upload_size_mb * BYTES_IN_MB)
    image_format = detect_image_format(data)
    if image_format is None:
        raise UnsupportedImageError(
            f"Загрузить можно только изображение: {', '.join(SUPPORTED_CONTENT_TYPES)}",
            details=[{"loc": ["body", "file"], "msg": "Это не изображение"}],
        )

    # the tenant owns its prefix, so a key cannot be confused with another business's
    key = f"products/{business_id}/{product.id}/{uuid.uuid4().hex}{image_format.extension}"
    # the row goes in before the upload: a failed upload rolls the transaction back and
    # leaves nothing behind, while the reverse order would strand an object in the bucket
    image = await product_images.add(
        session,
        ProductImage(
            product_id=product.id,
            image_url=storage.public_url(settings, key),
            sort_order=await product_images.next_sort_order(session, product.id),
            alt_text=alt_text,
        ),
    )
    await storage.put_object(settings, key, data, image_format.content_type)
    return image


async def remove_image(
    session: AsyncSession,
    settings: Settings,
    business_id: uuid.UUID,
    product_id: uuid.UUID,
    image_id: uuid.UUID,
) -> str | None:
    """Deletes the row and answers with the object key, for the caller to drop after it commits."""
    product = await products_service.get_owned_product(session, business_id, product_id)
    image = await product_images.get_owned(session, product.id, image_id)
    if image is None:
        raise ImageNotFoundError("Фото не найдено")
    key = storage.key_from_url(settings, image.image_url)
    await product_images.remove(session, image)
    return key


async def read_within_limit(upload: UploadFile, limit: int) -> bytes:
    """One byte over the limit is enough to refuse; the rest is never pulled into memory."""
    data = await upload.read(limit + 1)
    if len(data) > limit:
        raise ImageTooLargeError(f"Файл больше {limit // BYTES_IN_MB} МБ")
    return data
