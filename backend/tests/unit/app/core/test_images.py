import pytest

from app.core.images import GIF, JPEG, PNG, SIGNATURE_LENGTH, WEBP, detect_image_format

JPEG_BYTES = b"\xff\xd8\xff\xe0" + b"\x00" * 16
PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
GIF_BYTES = b"GIF89a" + b"\x00" * 16
WEBP_BYTES = b"RIFF" + b"\x24\x00\x00\x00" + b"WEBP" + b"\x00" * 16


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        (JPEG_BYTES, JPEG),
        (PNG_BYTES, PNG),
        (GIF_BYTES, GIF),
        (b"GIF87a" + b"\x00" * 16, GIF),
        (WEBP_BYTES, WEBP),
    ],
)
def test_a_known_format_is_recognised(data: bytes, expected: object) -> None:
    assert detect_image_format(data) is expected


@pytest.mark.parametrize(
    "data",
    [
        b"",  # nothing at all
        b"%PDF-1.7\n",  # a document
        b"MZ\x90\x00",  # a windows executable
        b"\x7fELF",  # a linux executable
        b'<svg xmlns="http://www.w3.org/2000/svg">',  # a document with scripts in it
        b"RIFF\x24\x00\x00\x00WAVE",  # the same container, but audio
        b"RIFF",  # a truncated header
        b"\xff\xd8",  # two of the three jpeg bytes
    ],
)
def test_anything_else_is_refused(data: bytes) -> None:
    assert detect_image_format(data) is None


def test_the_declared_type_does_not_matter() -> None:
    """An executable renamed to .jpg is still an executable — only the bytes are read."""
    assert detect_image_format(b"MZ\x90\x00" + JPEG_BYTES) is None


def test_the_signature_length_covers_every_format() -> None:
    """Whoever reads the head of a file reads this many bytes and needs no more."""
    assert detect_image_format(WEBP_BYTES[:SIGNATURE_LENGTH]) is WEBP
    assert detect_image_format(PNG_BYTES[:SIGNATURE_LENGTH]) is PNG
