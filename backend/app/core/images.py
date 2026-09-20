from typing import NamedTuple


class ImageFormat(NamedTuple):
    content_type: str
    extension: str


# the longest signature below, so one read of this many bytes settles every format
SIGNATURE_LENGTH = 12

JPEG = ImageFormat("image/jpeg", ".jpg")
PNG = ImageFormat("image/png", ".png")
GIF = ImageFormat("image/gif", ".gif")
WEBP = ImageFormat("image/webp", ".webp")

_PREFIXES: tuple[tuple[bytes, ImageFormat], ...] = (
    (b"\xff\xd8\xff", JPEG),
    (b"\x89PNG\r\n\x1a\n", PNG),
    (b"GIF87a", GIF),
    (b"GIF89a", GIF),
)

SUPPORTED_CONTENT_TYPES = (JPEG.content_type, PNG.content_type, GIF.content_type, WEBP.content_type)


def detect_image_format(data: bytes) -> ImageFormat | None:
    """Reads the format out of the bytes themselves.

    The Content-Type of a multipart part is written by the client, so it says what the
    sender wants us to believe. The signature says what the file is — an .exe renamed to
    .jpg does not get past this, and an SVG, which is a document with scripts in it rather
    than a picture, has no signature at all and is refused along with everything else.
    """
    for prefix, image_format in _PREFIXES:
        if data.startswith(prefix):
            return image_format
    # RIFF container: "RIFF" ---- "WEBP", the four bytes between are the chunk size
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return WEBP
    return None
