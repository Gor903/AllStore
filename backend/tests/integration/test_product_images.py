import uuid
from typing import TYPE_CHECKING, Any

import pytest
from httpx import AsyncClient, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

if TYPE_CHECKING:
    from mypy_boto3_s3.type_defs import GetObjectOutputTypeDef

from app.core.config import get_settings
from app.core.storage import build_s3_client, key_from_url
from app.models import ProductImage
from app.services.product_images import BYTES_IN_MB, MAX_IMAGES_PER_PRODUCT
from tests.integration.conftest import (
    PRODUCTS_URL,
    create_product,
    csrf_headers,
    register_buyer,
    register_second_seller,
    register_seller,
    seeded_category,
)

pytestmark = pytest.mark.integration

JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
GIF = b"GIF89a" + b"\x00" * 64
WEBP = b"RIFF\x40\x00\x00\x00WEBP" + b"\x00" * 64


def images_url(product_id: str) -> str:
    return f"{PRODUCTS_URL}/{product_id}/images"


async def upload(
    client: AsyncClient, product_id: str, data: bytes = JPEG, **fields: Any
) -> Response:
    """The declared filename and content type are the client's word — deliberately unreliable."""
    return await client.post(
        images_url(product_id),
        files={"file": ("photo.jpg", data, "image/jpeg")},
        data=fields,
        headers=csrf_headers(client),
    )


async def a_product(client: AsyncClient, session: AsyncSession) -> str:
    await register_seller(client)
    category = await seeded_category(session)
    created = await create_product(client, category.id)
    return str(created.json()["id"])


def stored_object(key: str) -> "GetObjectOutputTypeDef":
    settings = get_settings()
    return build_s3_client(settings).get_object(Bucket=settings.s3_bucket, Key=key)


def bucket_keys() -> list[str]:
    settings = get_settings()
    listing = build_s3_client(settings).list_objects_v2(Bucket=settings.s3_bucket)
    return [item["Key"] for item in listing.get("Contents", [])]


async def test_a_photo_lands_in_the_object_store(
    api_client: AsyncClient, session: AsyncSession, object_storage: None
) -> None:
    product_id = await a_product(api_client, session)

    response = await upload(api_client, product_id, alt_text="Кружка спереди")

    assert response.status_code == 201
    body = response.json()
    assert body["sort_order"] == 0
    assert body["alt_text"] == "Кружка спереди"
    key = key_from_url(get_settings(), body["image_url"])
    assert key is not None
    stored = stored_object(key)
    assert stored["Body"].read() == JPEG
    assert stored["ContentType"] == "image/jpeg"


async def test_the_key_is_filed_under_the_tenant(
    api_client: AsyncClient, session: AsyncSession, object_storage: None
) -> None:
    """A key of one business can never be mistaken for a key of another."""
    product_id = await a_product(api_client, session)

    body = (await upload(api_client, product_id)).json()

    key = key_from_url(get_settings(), body["image_url"])
    assert key is not None
    business_id = (await api_client.get(f"{PRODUCTS_URL}/{product_id}")).json()["business_id"]
    assert key.startswith(f"products/{business_id}/{product_id}/")


@pytest.mark.parametrize(
    ("data", "extension"),
    [(JPEG, ".jpg"), (PNG, ".png"), (GIF, ".gif"), (WEBP, ".webp")],
)
async def test_every_supported_format_is_accepted(
    api_client: AsyncClient,
    session: AsyncSession,
    object_storage: None,
    data: bytes,
    extension: str,
) -> None:
    product_id = await a_product(api_client, session)

    response = await upload(api_client, product_id, data=data)

    assert response.status_code == 201
    # the extension follows the bytes, not the .jpg the client wrote in the filename
    assert response.json()["image_url"].endswith(extension)


@pytest.mark.parametrize(
    "data",
    [
        b"%PDF-1.7\n" + b"\x00" * 64,  # a document
        b"MZ\x90\x00" + b"\x00" * 64,  # an executable renamed to .jpg
        b'<svg xmlns="http://www.w3.org/2000/svg"><script/></svg>',
        b"",  # nothing at all
    ],
)
async def test_a_file_that_is_not_an_image_is_refused(
    api_client: AsyncClient, session: AsyncSession, object_storage: None, data: bytes
) -> None:
    product_id = await a_product(api_client, session)

    response = await upload(api_client, product_id, data=data)

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "unsupported_image_type"
    assert error["details"][0]["loc"] == ["body", "file"]
    assert bucket_keys() == []


async def test_a_file_over_the_limit_is_refused(
    api_client: AsyncClient, session: AsyncSession, object_storage: None
) -> None:
    product_id = await a_product(api_client, session)
    oversized = JPEG + b"\x00" * (get_settings().max_upload_size_mb * BYTES_IN_MB)

    response = await upload(api_client, product_id, data=oversized)

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "image_too_large"
    assert bucket_keys() == []


async def test_a_refused_upload_leaves_no_row(
    api_client: AsyncClient, session: AsyncSession, object_storage: None
) -> None:
    product_id = await a_product(api_client, session)

    await upload(api_client, product_id, data=b"%PDF-1.7\n")

    rows = await session.execute(
        select(ProductImage).where(ProductImage.product_id == uuid.UUID(product_id))
    )
    assert rows.scalars().all() == []


async def test_a_second_photo_goes_to_the_end_of_the_gallery(
    api_client: AsyncClient, session: AsyncSession, object_storage: None
) -> None:
    product_id = await a_product(api_client, session)
    assert (await upload(api_client, product_id)).json()["sort_order"] == 0

    response = await upload(api_client, product_id, data=PNG)

    assert response.json()["sort_order"] == 1


async def test_the_gallery_comes_with_the_product(
    api_client: AsyncClient, session: AsyncSession, object_storage: None
) -> None:
    product_id = await a_product(api_client, session)
    await upload(api_client, product_id, data=PNG)
    await upload(api_client, product_id, data=JPEG)

    response = await api_client.get(f"{PRODUCTS_URL}/{product_id}")

    images = response.json()["images"]
    assert [image["sort_order"] for image in images] == [0, 1]
    assert (await api_client.get(PRODUCTS_URL)).json()["items"][0]["images"] == images


async def test_a_product_without_photos_reports_an_empty_gallery(
    api_client: AsyncClient, session: AsyncSession
) -> None:
    product_id = await a_product(api_client, session)

    response = await api_client.get(f"{PRODUCTS_URL}/{product_id}")

    assert response.json()["images"] == []


async def test_the_gallery_has_a_ceiling(
    api_client: AsyncClient, session: AsyncSession, object_storage: None
) -> None:
    product_id = await a_product(api_client, session)
    for _ in range(MAX_IMAGES_PER_PRODUCT):
        assert (await upload(api_client, product_id)).status_code == 201

    response = await upload(api_client, product_id)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "image_limit_reached"


async def test_a_photo_cannot_be_added_to_a_foreign_product(
    api_client: AsyncClient, session: AsyncSession, object_storage: None
) -> None:
    product_id = await a_product(api_client, session)
    await register_second_seller(api_client, session)

    response = await upload(api_client, product_id)

    assert response.status_code == 404
    assert bucket_keys() == []


async def test_a_photo_cannot_be_added_to_an_archived_product(
    api_client: AsyncClient, session: AsyncSession, object_storage: None
) -> None:
    product_id = await a_product(api_client, session)
    await api_client.delete(f"{PRODUCTS_URL}/{product_id}", headers=csrf_headers(api_client))

    response = await upload(api_client, product_id)

    assert response.status_code == 404


async def test_a_buyer_cannot_add_a_photo(api_client: AsyncClient, object_storage: None) -> None:
    await register_buyer(api_client)

    response = await upload(api_client, str(uuid.uuid4()))

    assert response.status_code == 403


async def test_an_upload_without_the_csrf_header_is_forbidden(
    api_client: AsyncClient, session: AsyncSession, object_storage: None
) -> None:
    product_id = await a_product(api_client, session)

    response = await api_client.post(
        images_url(product_id), files={"file": ("photo.jpg", JPEG, "image/jpeg")}
    )

    assert response.status_code == 403


async def test_a_photo_is_deleted_from_the_row_and_the_bucket(
    api_client: AsyncClient, session: AsyncSession, object_storage: None
) -> None:
    product_id = await a_product(api_client, session)
    image = (await upload(api_client, product_id)).json()

    response = await api_client.delete(
        f"{images_url(product_id)}/{image['id']}", headers=csrf_headers(api_client)
    )

    assert response.status_code == 204
    assert bucket_keys() == []
    assert (await api_client.get(f"{PRODUCTS_URL}/{product_id}")).json()["images"] == []


async def test_an_unknown_photo_is_not_found(
    api_client: AsyncClient, session: AsyncSession, object_storage: None
) -> None:
    product_id = await a_product(api_client, session)

    response = await api_client.delete(
        f"{images_url(product_id)}/{uuid.uuid4()}", headers=csrf_headers(api_client)
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "image_not_found"


async def test_a_foreign_photo_cannot_be_deleted(
    api_client: AsyncClient, session: AsyncSession, object_storage: None
) -> None:
    product_id = await a_product(api_client, session)
    image = (await upload(api_client, product_id)).json()
    await register_second_seller(api_client, session)

    response = await api_client.delete(
        f"{images_url(product_id)}/{image['id']}", headers=csrf_headers(api_client)
    )

    assert response.status_code == 404
    assert bucket_keys() != []
