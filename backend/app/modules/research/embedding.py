"""Text embeddings for research retrieval (P12-T05), behind a replaceable interface.

Only the deterministic `HashEmbedder` exists today (approved for P12: no external embedding
service). It hashes word tokens into a fixed number of dimensions and normalises the vector, so
equal texts always give equal vectors and texts sharing words are close. It is good enough to
test retrieval end to end; the production model is chosen before launch (an embedding API, which
would receive public research text only, never user data, or a local model). Changing the model
means re-embedding every item: each row records the model that embedded it."""

import hashlib
import math
import re
from collections.abc import Sequence
from itertools import pairwise
from typing import Protocol

DIMENSIONS = 256
_TOKEN = re.compile(r"[a-z0-9]+")
_STOP = frozenset(
    [
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "for",
        "from",
        "has",
        "have",
        "in",
        "is",
        "it",
        "its",
        "of",
        "on",
        "or",
        "that",
        "the",
        "this",
        "to",
        "was",
        "were",
        "will",
        "with",
    ]
)


class Embedder(Protocol):
    name: str
    dimensions: int

    def embed(self, texts: Sequence[str]) -> list[list[float]]: ...


def tokens(text: str) -> list[str]:
    return [t for t in _TOKEN.findall(text.lower()) if t not in _STOP]


class HashEmbedder:
    """Feature hashing of word unigrams and bigrams; L2-normalised; deterministic."""

    name = "hash-v1"
    dimensions = DIMENSIONS

    def _vector(self, text: str) -> list[float]:
        words = tokens(text)
        features = words + [f"{a} {b}" for a, b in pairwise(words)]
        vec = [0.0] * self.dimensions
        for feature in features:
            digest = hashlib.blake2b(feature.encode(), digest_size=8).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimensions
            sign = 1.0 if digest[4] & 1 else -1.0
            vec[index] += sign
        norm = math.sqrt(sum(v * v for v in vec))
        return [v / norm for v in vec] if norm else vec

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._vector(t) for t in texts]


def build_embedder(model: str) -> Embedder:
    """The configured embedder (`RESEARCH_EMBEDDER`). Only the deterministic hash model exists."""
    if model == "hash":
        return HashEmbedder()
    raise ValueError(f"unknown research embedder: {model}")
