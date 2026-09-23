import math

from app.embedder import FakeEmbedder


def test_the_same_text_gives_the_same_vector() -> None:
    embedder = FakeEmbedder(dimensions=8)

    assert embedder.embed_query("ваза") == embedder.embed_query("ваза")


def test_different_texts_give_different_vectors() -> None:
    embedder = FakeEmbedder(dimensions=8)

    assert embedder.embed_query("ваза") != embedder.embed_query("плед")


def test_vectors_are_normalised() -> None:
    """Cosine distance is only meaningful on unit vectors — the stand-in has to behave."""
    embedder = FakeEmbedder(dimensions=16)

    length = math.sqrt(sum(value * value for value in embedder.embed_query("ваза")))

    assert length == 0 or abs(length - 1.0) < 1e-9


def test_the_width_is_what_was_asked_for() -> None:
    assert len(FakeEmbedder(dimensions=1024).embed_query("ваза")) == 1024
    assert [len(v) for v in FakeEmbedder(4).embed_documents(["а", "б"])] == [4, 4]
