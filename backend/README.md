# Orange Reader — backend (ingestion)

PDF → text → chunks → embeddings → Postgres/pgvector. Text only for now; each step
is one replaceable function in `ingest/`. No API layer yet.

```
config.py            env-driven settings (RABBIT_*)
db.py                connections, schema apply, test/stress DB creation
schema.sql           books + chunks tables (idempotent)
embedder/            embedding boundary — standalone, moves to its own branch/service
ingest/
  extract.py         extract_pages(pdf_path)
  clean.py           clean_text(pages)            -> .needs_ocr flag
  chunk.py           chunk_pages(pages, size, overlap)
  embed.py           embed_chunks(chunks, batch_size)
  save.py            save_chunks(book_id, chunks, vectors, ...)
  pipeline.py        ingest_book(book_id, pdf_path, on_progress)
  library.py         add_book / reindex_book / delete_book / list_books
  __main__.py        CLI
tests/               pytest (unit + integration)
stress/              synthetic PDF generator + stress runner
```

## Setup

```bash
docker compose -f ../docker-compose.yml up -d   # Postgres 16 + pgvector (compose file lives at the project root)
uv pip install -r requirements.txt              # into ../../.venv
python -m ingest init-db                        # apply schema.sql (safe to repeat)
```

Run everything from this `backend/` directory with `../../.venv/bin/python` (or an activated venv).

## CLI

```bash
python -m ingest add path/to/book.pdf --title "Title" [--author "Name"]
python -m ingest reindex <book_id>
python -m ingest list
python -m ingest delete <book_id>      # chunks cascade
```

## Embedder boundary

`ingest` only uses `embedder.get_embedder()` (`embed_documents`, `model_name`, `dim`)
and `embedder.get_tokenizer()` (`count`, `offsets`). Today the backend is `local`
(sentence-transformers in-process, fp16 on CUDA, GPU calls serialised by a lock).
To split it out: add an HTTP server around `LocalEmbedder` and an `HttpEmbedder`
client registered as `RABBIT_EMBED_BACKEND=http`. The tokenizer stays local (no weights).

## Tests

```bash
python -m pytest                     # all (integration uses DB orange_rabbit_test + GPU)
python -m pytest -m "not integration"
```

## Stress tests

```bash
python -m stress.stress_ingest                         # all scenarios, ~6 min
python -m stress.stress_ingest throughput --books 5 --pages 300
python -m stress.stress_ingest concurrent --workers 8
python -m stress.make_pdf book out.pdf --pages 250     # just make a synthetic PDF
```

Scenarios: `throughput`, `reindex` (idempotence), `concurrent` (parallel adds, parallel
reindex of one book, duplicate-upload race), `failures` (scanned/encrypted/corrupt/
duplicate/missing source), `large` (1200 pages), then `cascade` (delete everything).
Uses its own DB `orange_rabbit_stress` and `stress/out/`; JSON report in `stress/out/`.

Baseline (RTX 5060 Laptop, fp16, batch 16): ~16 pages/s, ~15 s per 250-page book
(embedding ≈ 90%), 1200 pages in 73 s, 2.4 GB peak VRAM.
