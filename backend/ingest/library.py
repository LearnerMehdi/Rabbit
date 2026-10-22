"""Book-level operations the UI/API will call."""
import hashlib
import shutil
import uuid
from pathlib import Path
from uuid import UUID

import psycopg

import config
import db

from .pipeline import ingest_book
from .types import BookNotFoundError, DuplicateBookError, IngestResult, ProgressFn


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def add_book(
    pdf_path: Path,
    title: str,
    author: str | None = None,
    on_progress: ProgressFn | None = None,
    *,
    db_url: str | None = None,
    books_dir: Path | None = None,
) -> UUID:
    """Copy into the library, create the book row, and index it. Returns the book id.

    Raises DuplicateBookError if a file with the same SHA-256 is already in the library.
    If indexing fails the row stays with status 'failed' and the error is re-raised.
    """
    pdf_path = Path(pdf_path)
    if not pdf_path.is_file():
        raise FileNotFoundError(pdf_path)
    digest = sha256_file(pdf_path)
    book_id = uuid.uuid4()
    dest = Path(books_dir or config.BOOKS_DIR) / str(book_id) / "source.pdf"

    with db.connect(db_url) as conn:
        existing = conn.execute("SELECT id FROM books WHERE file_sha256 = %s", (digest,)).fetchone()
        if existing:
            raise DuplicateBookError(existing[0])
        try:
            conn.execute(
                "INSERT INTO books (id, title, author, file_path, file_sha256, status)"
                " VALUES (%s, %s, %s, %s, %s, 'indexing')",
                (book_id, title, author, str(dest), digest),
            )
        except psycopg.errors.UniqueViolation:  # lost a race with an identical upload
            conn.rollback()
            existing = conn.execute("SELECT id FROM books WHERE file_sha256 = %s", (digest,)).fetchone()
            raise DuplicateBookError(existing[0] if existing else None) from None

    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(pdf_path, dest)
    except Exception:
        delete_book(book_id, db_url=db_url, books_dir=books_dir)
        raise

    ingest_book(book_id, dest, on_progress, db_url=db_url)
    return book_id


def reindex_book(book_id: UUID, on_progress: ProgressFn | None = None, *, db_url: str | None = None) -> IngestResult:
    with db.connect(db_url) as conn:
        row = conn.execute("SELECT file_path FROM books WHERE id = %s", (book_id,)).fetchone()
    if not row:
        raise BookNotFoundError(f"Book {book_id} not found")
    return ingest_book(book_id, Path(row[0]), on_progress, db_url=db_url)


def delete_book(book_id: UUID, *, db_url: str | None = None, books_dir: Path | None = None) -> bool:
    """Delete the row (chunks cascade) and the stored file. True if a row was deleted."""
    with db.connect(db_url) as conn:
        deleted = conn.execute("DELETE FROM books WHERE id = %s", (book_id,)).rowcount
    shutil.rmtree(Path(books_dir or config.BOOKS_DIR) / str(book_id), ignore_errors=True)
    return bool(deleted)


def list_books(*, db_url: str | None = None) -> list[dict]:
    with db.connect(db_url) as conn:
        cur = conn.execute(
            "SELECT b.id, b.title, b.author, b.status, b.page_count, b.error,"
            " (SELECT count(*) FROM chunks c WHERE c.book_id = b.id) AS chunks"
            " FROM books b ORDER BY b.created_at"
        )
        cols = [d.name for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]
