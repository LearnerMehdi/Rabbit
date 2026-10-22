from typing import Callable

import numpy as np

import config
from embedder import Embedder, get_embedder

from .types import Chunk


def embed_chunks(
    chunks: list[Chunk],
    batch_size: int | None = None,
    on_batch: Callable[[int, int], None] | None = None,
    embedder: Embedder | None = None,
) -> np.ndarray:
    """(len(chunks), dim) normalised vectors. `on_batch(done, total)` after each batch."""
    batch_size = batch_size or config.EMBED_BATCH_SIZE
    emb = embedder or get_embedder()
    texts = [c.content for c in chunks]
    out = np.empty((len(texts), emb.dim), dtype=np.float32)
    for i in range(0, len(texts), batch_size):
        out[i : i + batch_size] = emb.embed_documents(texts[i : i + batch_size])
        if on_batch:
            on_batch(min(i + batch_size, len(texts)), len(texts))
    return out
