"""Embedding service boundary.

Everything outside this package talks to embeddings only through `Embedder` and
`Tokenizer` (see base.py) and the two factories below. The package has no
imports from the rest of the project so it can be split into its own
service/branch; the ingestion side would then use an HTTP-backed `Embedder`
with the same interface.
"""
from .base import Embedder, Tokenizer
from .factory import get_embedder, get_tokenizer

__all__ = ["Embedder", "Tokenizer", "get_embedder", "get_tokenizer"]
