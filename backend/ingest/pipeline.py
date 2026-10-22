import logging
import time
from pathlib import Path
from uuid import UUID

import config
import db
from embedder import Embedder, get_embedder

from .chunk import chunk_pages
from .clean import clean_text
from .embed import embed_chunks
from .extract import extract_pages
from .save import save_chunks
from .types import IngestError, IngestResult, NoTextLayerError, ProgressFn

log = logging.getLogger(__name__)

# overall percent at which each stage starts
STAGE_START = {"extracting": 0.0, "chunking": 10.0, "embedding": 20.0, "saving": 90.0, "ready": 100.0}


def _set_status(book_id: UUID, status: str, error: str | None, db_url: str | None) -> None:
    with db.connect(db_url) as conn:
        conn.execute("UPDATE books SET status = %s, error = %s WHERE id = %s", (status, error, book_id))


def _short_error(e: Exception) -> str:
    msg = str(e) if isinstance(e, IngestError) else f"{type(e).__name__}: {e}"
    return msg.strip()[:300] or type(e).__name__


def ingest_book(
    book_id: UUID,
    pdf_path: Path,
    on_progress: ProgressFn | None = None,
    *,
    embedder: Embedder | None = None,
    db_url: str | None = None,
) -> IngestResult:
    t0 = time.perf_counter()
    percent = 0.0

    def report(stage: str, pct: float):
        nonlocal percent
        percent = pct
        if on_progress:
            on_progress(stage, round(pct, 1))

    try:
        _set_status(book_id, "indexing", None, db_url)

        report("extracting", STAGE_START["extracting"])
        pages = extract_pages(Path(pdf_path))

        report("chunking", STAGE_START["chunking"])
        pages = clean_text(pages)
        if pages.needs_ocr:
            raise NoTextLayerError()
        chunks = chunk_pages(pages)

        emb = embedder or get_embedder()
        report("embedding", STAGE_START["embedding"])
        span = STAGE_START["saving"] - STAGE_START["embedding"]
        vectors = embed_chunks(
            chunks,
            on_batch=lambda done, total: report("embedding", STAGE_START["embedding"] + span * done / total),
            embedder=emb,
        )

        report("saving", STAGE_START["saving"])
        save_chunks(
            book_id, chunks, vectors,
            page_count=pages.page_count, embed_model=emb.model_name, embed_dim=emb.dim, db_url=db_url,
        )
        report("ready", STAGE_START["ready"])
    except Exception as e:
        log.exception("ingest failed for book %s", book_id)
        try:
            _set_status(book_id, "failed", _short_error(e), db_url)
        except Exception:
            log.exception("could not mark book %s failed", book_id)
        if on_progress:
            on_progress("failed", round(percent, 1))
        raise

    return IngestResult(
        book_id=str(book_id),
        page_count=pages.page_count,
        chunk_count=len(chunks),
        empty_page_count=pages.empty_pages,
        duration_s=time.perf_counter() - t0,
    )
