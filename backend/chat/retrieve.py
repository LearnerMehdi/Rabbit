"""Top-k chunks of one book for a question: embed the question, sort by distance, take k.

No re-ranking, query rewriting or score threshold.
"""
from dataclasses import dataclass
from uuid import UUID

import config
import db
from embedder import Embedder, get_embedder


@dataclass
class Excerpt:
    page_start: int
    page_end: int
    content: str
    distance: float  # cosine distance, 0 = same direction


def search_chunks(
    book_id: UUID,
    question: str,
    k: int | None = None,
    *,
    embedder: Embedder | None = None,
    db_url: str | None = None,
) -> list[Excerpt]:
    """The `k` chunks of the book closest to `question`, closest first."""
    k = k or config.CHAT_TOP_K
    [q] = (embedder or get_embedder()).embed_queries([question])
    with db.connect(db_url) as conn:
        rows = conn.execute(
            "SELECT page_start, page_end, content, embedding <=> %s AS distance"
            " FROM chunks WHERE book_id = %s ORDER BY distance LIMIT %s",
            (q, book_id, k),
        ).fetchall()
    return [Excerpt(*r) for r in rows]
