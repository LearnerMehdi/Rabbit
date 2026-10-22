import os
import threading

from .base import Embedder, Tokenizer

_lock = threading.Lock()
_embedders: dict[tuple, Embedder] = {}
_tokenizers: dict[str, Tokenizer] = {}

DEFAULT_MODEL = "Qwen/Qwen3-Embedding-0.6B"
DEFAULT_DIM = 1024


def get_embedder(
    backend: str | None = None,
    model_name: str | None = None,
    dim: int | None = None,
    device: str | None = None,
) -> Embedder:
    """Lazy process-wide singleton per (backend, model, device)."""
    backend = backend or os.environ.get("RABBIT_EMBED_BACKEND", "local")
    model_name = model_name or os.environ.get("RABBIT_EMBED_MODEL", DEFAULT_MODEL)
    dim = dim or int(os.environ.get("RABBIT_EMBED_DIM", DEFAULT_DIM))
    device = device or os.environ.get("RABBIT_EMBED_DEVICE", "auto")
    key = (backend, model_name, dim, device)
    with _lock:
        if key not in _embedders:
            if backend == "local":
                from .local import LocalEmbedder

                _embedders[key] = LocalEmbedder(model_name, dim, device)
            else:
                raise ValueError(f"unknown embed backend {backend!r}")
        return _embedders[key]


def get_tokenizer(model_name: str | None = None) -> Tokenizer:
    """Tokenizer only (no weights); stays local even when the embedder is remote."""
    model_name = model_name or os.environ.get("RABBIT_EMBED_MODEL", DEFAULT_MODEL)
    with _lock:
        if model_name not in _tokenizers:
            from .tokenizer import HFTokenizer

            _tokenizers[model_name] = HFTokenizer(model_name)
        return _tokenizers[model_name]
