import json

from app.core.config import get_settings
from app.core.storage import build_s3_client, delete_object, ensure_bucket, key_from_url, public_url

KEY = "products/b/p/photo.jpg"


def test_the_url_points_at_the_bucket_when_no_public_host_is_set() -> None:
    settings = get_settings().model_copy(
        update={"s3_endpoint_url": "http://minio:9000/", "s3_bucket": "shop", "s3_public_url": None}
    )

    assert public_url(settings, KEY) == f"http://minio:9000/shop/{KEY}"


def test_a_public_host_replaces_the_bucket_url() -> None:
    """In production the browser goes to the CDN, not to the storage endpoint."""
    settings = get_settings().model_copy(update={"s3_public_url": "https://cdn.allstore.am/"})

    assert public_url(settings, KEY) == f"https://cdn.allstore.am/{KEY}"


def test_the_key_is_read_back_out_of_the_url() -> None:
    settings = get_settings().model_copy(update={"s3_public_url": "https://cdn.allstore.am"})

    assert key_from_url(settings, public_url(settings, KEY)) == KEY


def test_a_url_from_somewhere_else_yields_no_key() -> None:
    """Nothing is deleted on the strength of a URL we did not write."""
    settings = get_settings().model_copy(update={"s3_public_url": "https://cdn.allstore.am"})

    assert key_from_url(settings, "https://evil.example/products/b/p/photo.jpg") is None


async def test_a_fresh_bucket_is_readable_by_a_browser(object_storage: None) -> None:
    """Without this the seller uploads a photo and the buyer's browser is refused it."""
    settings = get_settings().model_copy(update={"s3_bucket": "allstore-fresh"})

    await ensure_bucket(settings)

    policy = build_s3_client(settings).get_bucket_policy(Bucket=settings.s3_bucket)["Policy"]
    statement = json.loads(policy)["Statement"][0]
    assert statement["Action"] == "s3:GetObject"
    assert statement["Resource"] == "arn:aws:s3:::allstore-fresh/*"


async def test_an_existing_policy_is_left_alone(object_storage: None) -> None:
    """A bucket someone else set up may sit behind a CDN that wants something narrower."""
    settings = get_settings().model_copy(update={"s3_bucket": "allstore-managed"})
    client = build_s3_client(settings)
    client.create_bucket(Bucket=settings.s3_bucket)
    theirs = json.dumps(
        {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Deny",
                    "Principal": "*",
                    "Action": "s3:GetObject",
                    "Resource": "arn:aws:s3:::allstore-managed/*",
                }
            ],
        }
    )
    client.put_bucket_policy(Bucket=settings.s3_bucket, Policy=theirs)

    await ensure_bucket(settings)

    kept = client.get_bucket_policy(Bucket=settings.s3_bucket)["Policy"]
    assert json.loads(kept)["Statement"][0]["Effect"] == "Deny"


async def test_a_failed_deletion_is_logged_and_swallowed(object_storage: None) -> None:
    """The row is already gone by then — raising here would fail a request that succeeded."""
    settings = get_settings().model_copy(update={"s3_bucket": "no-such-bucket"})

    await delete_object(settings, KEY)
