import inspect
import logging
import threading

import numpy as np

log = logging.getLogger(__name__)


def resolve_device(device: str) -> str:
    if device != "auto":
        return device
    import torch

    return "cuda" if torch.cuda.is_available() else "cpu"


class LocalEmbedder:
    """sentence-transformers model running in this process."""

    def __init__(self, model_name: str, dim: int, device: str = "auto"):
        import torch
        from sentence_transformers import SentenceTransformer

        self.model_name = model_name
        self.device = resolve_device(device)
        log.info("loading %s on %s", model_name, self.device)
        model_kwargs = {"torch_dtype": torch.float16} if self.device == "cuda" else {}
        # sentence-transformers >= 6 renamed tokenizer_kwargs to processor_kwargs
        params = inspect.signature(SentenceTransformer.__init__).parameters
        tok_arg = "processor_kwargs" if "processor_kwargs" in params else "tokenizer_kwargs"
        self._model = SentenceTransformer(
            model_name,
            device=self.device,
            model_kwargs=model_kwargs,
            **{tok_arg: {"padding_side": "left"}},
        )
        get_dim = getattr(self._model, "get_embedding_dimension", None) or self._model.get_sentence_embedding_dimension
        self.dim = get_dim()
        if self.dim != dim:
            raise ValueError(f"{model_name} produces {self.dim}-dim vectors, expected {dim}")
        # One model, one GPU: serialise encode calls from concurrent ingest jobs.
        self._lock = threading.Lock()

    def _encode(self, texts: list[str], **kwargs) -> np.ndarray:
        if not texts:
            return np.empty((0, self.dim), dtype=np.float32)
        with self._lock:
            vecs = self._model.encode(
                texts,
                batch_size=len(texts),
                normalize_embeddings=True,
                convert_to_numpy=True,
                show_progress_bar=False,
                **kwargs,
            )
        return vecs.astype(np.float32, copy=False)

    def embed_documents(self, texts: list[str]) -> np.ndarray:
        return self._encode(texts)

    def embed_queries(self, texts: list[str]) -> np.ndarray:
        return self._encode(texts, prompt_name="query")
