# embedder

Embedding boundary for Orange Reader. Self-contained (imports nothing from the
rest of the repo) so it can move to its own branch/service.

- `Embedder` protocol: `model_name`, `dim`, `embed_documents(texts)`, `embed_queries(texts)`
  → L2-normalised float32 `(n, dim)` arrays.
- `Tokenizer` protocol: `count(text)`, `offsets(text)` — used by chunking.
- `get_embedder()` / `get_tokenizer()` — lazy singletons, configured by
  `RABBIT_EMBED_BACKEND` (`local`), `RABBIT_EMBED_MODEL`, `RABBIT_EMBED_DIM`, `RABBIT_EMBED_DEVICE`.

Planned: an HTTP server wrapping `LocalEmbedder`, plus an `HttpEmbedder` client
registered as backend `http` in `factory.py`. Callers don't change.
