from uuid import UUID

import numpy as np

import db

from .types import BookNotFoundError, Chunk


def save_chunks(
    book_id: UUID,
    chunks: list[Chunk],
    vectors: np.ndarray,
    *,
    page_count: int,
    embed_model: str,
    embed_dim: int,
    db_url: str | None = None,
) -> None:
    """Replace the book's chunks and mark it ready, in one transaction."""
    if len(chunks) != len(vectors):
        raise ValueError(f"{len(chunks)} chunks but {len(vectors)} vectors")
    with db.connect(db_url) as conn, conn.transaction():
        # row lock serialises concurrent re-index runs of the same book
        if not conn.execute("SELECT 1 FROM books WHERE id = %s FOR UPDATE", (book_id,)).fetchone():
            raise BookNotFoundError(f"Book {book_id} not found")
        conn.execute("DELETE FROM chunks WHERE book_id = %s", (book_id,))
        with conn.cursor().copy(
            "COPY chunks (book_id, ordinal, page_start, page_end, content, token_count, embedding)"
            " FROM STDIN WITH (FORMAT BINARY)"
        ) as copy:
            copy.set_types(["uuid", "int4", "int4", "int4", "text", "int4", "vector"])
            for c, v in zip(chunks, vectors):
                copy.write_row(
                    (book_id, c.ordinal, c.page_start, c.page_end, c.content, c.token_count, v)
                )
        conn.execute(
            "UPDATE books SET status = 'ready', error = NULL, page_count = %s,"
            " embed_model = %s, embed_dim = %s WHERE id = %s",
            (page_count, embed_model, embed_dim, book_id),
        )
