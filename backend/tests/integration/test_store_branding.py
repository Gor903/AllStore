import uuid
from typing import Any

import pytest
from httpx import AsyncClient, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.storage import key_from_url
from app.services.product_images import BYTES_IN_MB
from tests.integration.conftest import (
    a_live_shop,
    anonymous,
    csrf_headers,
    register_buyer,
    register_seller,
    seeded_category,
    switch,
)
from tests.integration.test_product_images import JPEG, PNG, bucket_keys, stored_object

pytestmark = pytest.mark.integration

STORES_URL = "/api/v1/stores"
ME_URL = f"{STORES_URL}/me"
STOREFRONT_URL = "/api/v1/storefront"


async def a_shopkeeper(client: AsyncClient, subdomain: str = "cups") -> str:
    """A seller with a storefront, which is what every branding request needs."""
    client.cookies.clear()
    await register_seller(client, email=f"seller-{uuid.uuid4().hex}@example.com")
    created = await client.post(
        STORES_URL, json={"subdomain": subdomain}, headers=csrf_headers(client)
    )
    assert created.status_code == 201
    return str(created.json()["id"])


async def patch_store(client: AsyncClient, **fields: Any) -> Response:
    return await client.patch(ME_URL, json=fields, headers=csrf_headers(client))


async def put_image(
    client: AsyncClient, kind: str = "logo", data: bytes = JPEG, name: str = "logo.jpg"
) -> Response:
    """The declared filename and content type are the client's word — deliberately unreliable."""
    return await client.put(
        f"{ME_URL}/images/{kind}",
        files={"file": (name, data, "image/jpeg")},
        headers=csrf_headers(client),
    )


async def test_a_seller_describes_their_shop(api_client: AsyncClient) -> None:
    await a_shopkeeper(api_client)

    response = await patch_store(api_client, description="Керамика ручной работы из Гюмри.")

    assert response.status_code == 200
    assert response.json()["description"] == "Керамика ручной работы из Гюмри."
    assert (await api_client.get(ME_URL)).json()[
        "description"
    ] == "Керамика ручной работы из Гюмри."


async def test_the_description_may_be_cleared(api_client: AsyncClient) -> None:
    await a_shopkeeper(api_client)
    await patch_store(api_client, description="Было описание")

    response = await patch_store(api_client, description=None)

    assert response.status_code == 200
    assert response.json()["description"] is None


async def test_an_absent_field_is_left_alone(api_client: AsyncClient) -> None:
    await a_shopkeeper(api_client)
    await patch_store(api_client, description="Описание", primary_color="#c4805c")

    await patch_store(api_client, primary_color="#343e4e")

    body = (await api_client.get(ME_URL)).json()
    assert body["description"] == "Описание"
    assert body["primary_color"] == "#343e4e"


async def test_a_colour_is_stored_in_one_shape(api_client: AsyncClient) -> None:
    await a_shopkeeper(api_client)

    response = await patch_store(api_client, primary_color="#C4805C", secondary_color="#EED6BA")

    assert response.status_code == 200
    assert response.json()["primary_color"] == "#c4805c"
    assert response.json()["secondary_color"] == "#eed6ba"


@pytest.mark.parametrize("colour", ["c4805c", "#c4805", "#ggg000", "красный", "#c4805c8", ""])
async def test_a_value_that_is_not_a_colour_is_rejected(
    api_client: AsyncClient, colour: str
) -> None:
    await a_shopkeeper(api_client)

    response = await patch_store(api_client, primary_color=colour)

    assert response.status_code == 422
    assert (await api_client.get(ME_URL)).json()["primary_color"] is None


async def test_a_colour_may_be_cleared_back_to_the_theme(api_client: AsyncClient) -> None:
    await a_shopkeeper(api_client)
    await patch_store(api_client, primary_color="#c4805c")

    response = await patch_store(api_client, primary_color=None)

    assert response.status_code == 200
    assert response.json()["primary_color"] is None


async def test_an_unknown_theme_is_refused(api_client: AsyncClient) -> None:
    """A theme the storefront cannot render would be a look the seller never gets."""
    await a_shopkeeper(api_client)

    response = await patch_store(api_client, theme_id="neon")

    assert response.status_code == 422
    assert (await api_client.get(ME_URL)).json()["theme_id"] == "default"


async def test_the_theme_cannot_be_cleared(api_client: AsyncClient) -> None:
    await a_shopkeeper(api_client)

    response = await patch_store(api_client, theme_id=None)

    assert response.status_code == 422


async def test_an_unknown_field_is_refused(api_client: AsyncClient) -> None:
    """The subdomain is the address the seller already gave out — not editable here."""
    await a_shopkeeper(api_client)

    response = await patch_store(api_client, subdomain="other")

    assert response.status_code == 422


async def test_a_logo_lands_in_the_object_store(
    api_client: AsyncClient, object_storage: None
) -> None:
    store_id = await a_shopkeeper(api_client)

    response = await put_image(api_client)

    assert response.status_code == 200
    key = key_from_url(get_settings(), response.json()["logo_url"])
    assert key is not None
    assert stored_object(key)["Body"].read() == JPEG
    business_id = (await api_client.get(ME_URL)).json()["business_id"]
    # a key of one business can never be mistaken for a key of another
    assert key.startswith(f"stores/{business_id}/logo/")
    assert store_id == (await api_client.get(ME_URL)).json()["id"]


async def test_a_banner_is_kept_apart_from_the_logo(
    api_client: AsyncClient, object_storage: None
) -> None:
    await a_shopkeeper(api_client)

    await put_image(api_client, kind="logo")
    body = (await put_image(api_client, kind="banner", data=PNG)).json()

    assert body["logo_url"] is not None
    assert body["banner_url"] is not None
    assert body["logo_url"] != body["banner_url"]
    key = key_from_url(get_settings(), body["banner_url"])
    assert key is not None
    assert "/banner/" in key


async def test_a_second_upload_replaces_the_first(
    api_client: AsyncClient, object_storage: None
) -> None:
    """One logo per storefront: the displaced object goes, so the bucket does not grow
    by one file every time a seller tries another picture."""
    await a_shopkeeper(api_client)
    first = (await put_image(api_client)).json()["logo_url"]
    old_key = key_from_url(get_settings(), first)

    second = (await put_image(api_client, data=PNG)).json()["logo_url"]

    assert second != first
    assert old_key not in bucket_keys()
    assert key_from_url(get_settings(), second) in bucket_keys()


async def test_a_cleared_logo_leaves_no_object_behind(
    api_client: AsyncClient, object_storage: None
) -> None:
    await a_shopkeeper(api_client)
    uploaded = (await put_image(api_client)).json()["logo_url"]
    key = key_from_url(get_settings(), uploaded)

    response = await api_client.delete(f"{ME_URL}/images/logo", headers=csrf_headers(api_client))

    assert response.status_code == 200
    assert response.json()["logo_url"] is None
    assert key not in bucket_keys()


async def test_clearing_a_logo_that_is_not_there_is_not_an_error(
    api_client: AsyncClient, object_storage: None
) -> None:
    await a_shopkeeper(api_client)

    response = await api_client.delete(f"{ME_URL}/images/logo", headers=csrf_headers(api_client))

    assert response.status_code == 200
    assert response.json()["logo_url"] is None


async def test_a_file_that_is_not_an_image_is_refused(
    api_client: AsyncClient, object_storage: None
) -> None:
    """The content type of a part is written by the sender; the signature is not."""
    await a_shopkeeper(api_client)

    response = await put_image(api_client, data=b"MZ\x90\x00" + b"\x00" * 64)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "unsupported_image_type"
    assert (await api_client.get(ME_URL)).json()["logo_url"] is None


async def test_a_file_over_the_limit_is_refused(
    api_client: AsyncClient, object_storage: None
) -> None:
    await a_shopkeeper(api_client)
    too_big = JPEG + b"\x00" * (get_settings().max_upload_size_mb * BYTES_IN_MB)

    response = await put_image(api_client, data=too_big)

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "image_too_large"


async def test_an_unknown_kind_is_not_a_route(api_client: AsyncClient) -> None:
    await a_shopkeeper(api_client)

    response = await put_image(api_client, kind="favicon")

    assert response.status_code == 422


async def test_the_contacts_route_is_not_swallowed_by_the_image_route(
    api_client: AsyncClient,
) -> None:
    """`/stores/me/contacts` and `/stores/me/images/{kind}` live next to each other."""
    await a_shopkeeper(api_client)

    response = await api_client.put(
        f"{ME_URL}/contacts",
        json={"items": [{"platform": "phone", "value": "+37410123456"}]},
        headers=csrf_headers(api_client),
    )

    assert response.status_code == 200
    assert response.json()["items"][0]["platform"] == "phone"


async def test_a_seller_does_not_dress_another_sellers_shop(api_client: AsyncClient) -> None:
    await a_shopkeeper(api_client, "cups")
    await patch_store(api_client, description="Первая лавка", primary_color="#c4805c")
    first = dict(api_client.cookies)

    await a_shopkeeper(api_client, "plates")
    await patch_store(api_client, description="Вторая лавка", primary_color="#343e4e")

    api_client.cookies.clear()
    api_client.cookies.update(first)
    body = (await api_client.get(ME_URL)).json()
    assert body["description"] == "Первая лавка"
    assert body["primary_color"] == "#c4805c"
    assert body["subdomain"] == "cups"


async def test_a_seller_without_a_storefront_gets_404(api_client: AsyncClient) -> None:
    await register_seller(api_client, email=f"seller-{uuid.uuid4().hex}@example.com")

    response = await patch_store(api_client, description="Описание")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "store_not_found"


async def test_a_buyer_has_no_shop_to_dress(api_client: AsyncClient) -> None:
    await register_buyer(api_client)

    assert (await patch_store(api_client, description="Описание")).status_code == 403
    assert (await put_image(api_client)).status_code == 403


async def test_dressing_a_shop_without_the_csrf_header_is_forbidden(
    api_client: AsyncClient,
) -> None:
    await a_shopkeeper(api_client)

    response = await api_client.patch(ME_URL, json={"description": "Описание"})

    assert response.status_code == 403


async def test_the_storefront_shows_what_the_seller_set(
    api_client: AsyncClient, session: AsyncSession, object_storage: None
) -> None:

    shop = await a_live_shop(api_client, session, "cups")
    switch(api_client, shop.seller)
    await patch_store(
        api_client,
        description="Керамика ручной работы из Гюмри.",
        primary_color="#c4805c",
        secondary_color="#eed6ba",
    )
    await put_image(api_client, kind="logo")
    await put_image(api_client, kind="banner", data=PNG)
    await anonymous(api_client)

    body = (await api_client.get(f"{STOREFRONT_URL}/cups")).json()

    assert body["description"] == "Керамика ручной работы из Гюмри."
    assert body["primary_color"] == "#c4805c"
    assert body["secondary_color"] == "#eed6ba"
    assert body["logo_url"] is not None
    assert body["banner_url"] is not None
    assert await seeded_category(session) is not None
