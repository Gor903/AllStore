"""Turning text into vectors, and the one seam where that can be swapped.

Two implementations: the real model, and a deterministic stand-in. The stand-in exists because
a 2 GB download proves nothing about our code — CI and the tests run on it, and the real model
is exercised by hand on the stand.
"""

import hashlib
import math
import struct
from collections.abc import Sequence
from typing import Protocol

from app.config import Settings

# e5 models are trained with these prefixes and quietly lose accuracy without them: the same
# sentence means different things as a question and as an answer
QUERY_PREFIX = "query: "
DOCUMENT_PREFIX = "passage: "


class Embedder(Protocol):
    """A query and a document are embedded differently — the asymmetry is the point."""

    @property
    def name(self) -> str: ...

    @property
    def dimensions(self) -> int: ...

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...


class FakeEmbedder:
    """Deterministic vectors derived from the text itself.

    Not a similarity model and not pretending to be one: identical texts give identical
    vectors, different texts give different ones, and that is all a test of our plumbing
    needs. Anything about search quality has to be checked against the real model.
    """

    def __init__(self, dimensions: int) -> None:
        self._dimensions = dimensions

    @property
    def name(self) -> str:
        return f"fake-{self._dimensions}"

    @property
    def dimensions(self) -> int:
        return self._dimensions

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._vector(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vector(text)

    def _vector(self, text: str) -> list[float]:
        # the hash is stretched to the required width, then normalised, so cosine distance
        # behaves the same way it does with a real model
        raw = bytearray()
        counter = 0
        while len(raw) < self._dimensions * 4:
            raw.extend(hashlib.sha256(f"{counter}:{text}".encode()).digest())
            counter += 1
        numbers = [
            struct.unpack_from(">i", raw, offset * 4)[0] / 2**31
            for offset in range(self._dimensions)
        ]
        length = math.sqrt(sum(number * number for number in numbers)) or 1.0
        return [number / length for number in numbers]


class FastEmbedEmbedder:
    """The real model, ONNX on CPU — no torch in the image, no GPU on the stand."""

    def __init__(self, model_name: str, dimensions: int) -> None:
        from fastembed import TextEmbedding

        self._model_name = model_name
        self._dimensions = dimensions
        self._model = TextEmbedding(model_name=model_name)

    @property
    def name(self) -> str:
        return self._model_name

    @property
    def dimensions(self) -> int:
        return self._dimensions

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        prefixed = [f"{DOCUMENT_PREFIX}{text}" for text in texts]
        return [vector.tolist() for vector in self._model.embed(prefixed)]

    def embed_query(self, text: str) -> list[float]:
        vectors = list(self._model.query_embed(f"{QUERY_PREFIX}{text}"))
        return list(vectors[0].tolist())


def build_embedder(settings: Settings) -> Embedder:
    if settings.embedder == "fake":
        return FakeEmbedder(settings.embedding_dimensions)
    return FastEmbedEmbedder(settings.embedding_model, settings.embedding_dimensions)
