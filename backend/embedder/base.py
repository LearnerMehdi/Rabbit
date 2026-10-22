from typing import Protocol, runtime_checkable

import numpy as np


@runtime_checkable
class Tokenizer(Protocol):
    def count(self, text: str) -> int:
        """Number of model tokens in `text` (no special tokens)."""

    def offsets(self, text: str) -> list[tuple[int, int]]:
        """Character span of every token in `text`, in order."""


@runtime_checkable
class Embedder(Protocol):
    model_name: str
    dim: int

    def embed_documents(self, texts: list[str]) -> np.ndarray:
        """L2-normalised float32 vectors, shape (len(texts), dim). No instruction prefix."""

    def embed_queries(self, texts: list[str]) -> np.ndarray:
        """L2-normalised float32 vectors with the model's query instruction prefix."""
