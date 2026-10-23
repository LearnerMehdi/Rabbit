"""Book-level operations the UI/API will call."""
import hashlib
import logging
import shutil
import uuid
from pathlib import Path
from uuid import UUID

import psycopg
import pymupdf as fitz

import config
import db

from .pipeline import ingest_book
from .types import BookNotFoundError, DuplicateBookError, IngestResult, NotPdfError, ProgressFn

log = logging.getLogger(__name__)

COVER_NAME = "cover.jpg"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def is_pdf(path: Path) -> bool:
    with open(path, "rb") as f:
        return b"%PDF-" in f.read(1024)


def make_cover(pdf_path: Path, dest: Path, width: int = 272) -> bool:
    """First page as a JPEG thumbnail. False if the PDF can't be rendered (e.g. encrypted)."""
    try:
        with fitz.open(pdf_path) as doc:
            if doc.needs_pass or doc.page_count == 0:
                return False
            page = doc[0]
            zoom = width / page.rect.width
            page.get_pixmap(matrix=fitz.Matrix(zoom, zoom)).save(dest, jpg_quality=85)
        return True
    except Exception:
        log.warning("no cover for %s", pdf_path, exc_info=True)
        return False


def create_book(
    pdf_path: Path,
    title: str,
    author: str | None = None,
    *,
    file_name: str | None = None,
    db_url: str | None = None,
    books_dir: Path | None = None,
) -> UUID:
    """Copy into the library and create the book row ('indexing'), without indexing it.

    Raises NotPdfError for files without a PDF header and DuplicateBookError if a file
    with the same SHA-256 is already in the library.
    """
    pdf_path = Path(pdf_path)
    if not pdf_path.is_file():
        raise FileNotFoundError(pdf_path)
    if not is_pdf(pdf_path):
        raise NotPdfError()
    digest = sha256_file(pdf_path)
    book_id = uuid.uuid4()
    dest = Path(books_dir or config.BOOKS_DIR) / str(book_id) / "source.pdf"

    with db.connect(db_url) as conn:
        existing = conn.execute("SELECT id FROM books WHERE file_sha256 = %s", (digest,)).fetchone()
        if existing:
            raise DuplicateBookError(existing[0])
        try:
            conn.execute(
                "INSERT INTO books (id, title, author, file_path, file_sha256, file_name, file_size, status)"
                " VALUES (%s, %s, %s, %s, %s, %s, %s, 'indexing')",
                (book_id, title, author, str(dest), digest, file_name or pdf_path.name, pdf_path.stat().st_size),
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
    make_cover(dest, dest.with_name(COVER_NAME))
    return book_id


def add_book(
    pdf_path: Path,
    title: str,
    author: str | None = None,
    on_progress: ProgressFn | None = None,
    *,
    db_url: str | None = None,
    books_dir: Path | None = None,
) -> UUID:
    """create_book, then index it. Returns the book id.

    If indexing fails the row stays with status 'failed' and the error is re-raised.
    """
    book_id = create_book(pdf_path, title, author, db_url=db_url, books_dir=books_dir)
    dest = Path(books_dir or config.BOOKS_DIR) / str(book_id) / "source.pdf"
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


_BOOK_COLUMNS = (
    "b.id, b.title, b.author, b.status, b.page_count, b.error, b.file_path, b.file_name, b.file_size,"
    " b.last_page, b.last_opened_at, b.created_at,"
    " (SELECT count(*) FROM chunks c WHERE c.book_id = b.id) AS chunks"
)
_ORDER = {
    "added": "b.created_at DESC",
    "title": "lower(b.title), b.created_at DESC",
    "opened": "b.last_opened_at DESC NULLS LAST, b.created_at DESC",
}


def _rows(cur) -> list[dict]:
    cols = [d.name for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def list_books(query: str = "", sort: str = "added", *, db_url: str | None = None) -> list[dict]:
    """Books matching `query` (title or author) in `sort` order: added | title | opened."""
    where, params = "", []
    if query.strip():
        where = " WHERE b.title ILIKE %s OR b.author ILIKE %s"
        like = "%" + query.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        params = [like, like]
    with db.connect(db_url) as conn:
        cur = conn.execute(f"SELECT {_BOOK_COLUMNS} FROM books b{where} ORDER BY {_ORDER[sort]}", params)
        return _rows(cur)


def get_book(book_id: UUID, *, db_url: str | None = None) -> dict:
    with db.connect(db_url) as conn:
        rows = _rows(conn.execute(f"SELECT {_BOOK_COLUMNS} FROM books b WHERE b.id = %s", (book_id,)))
    if not rows:
        raise BookNotFoundError(f"Book {book_id} not found")
    return rows[0]


def _update(book_id: UUID, assignments: str, params: tuple, db_url: str | None) -> None:
    with db.connect(db_url) as conn:
        if not conn.execute(f"UPDATE books SET {assignments} WHERE id = %s", (*params, book_id)).rowcount:
            raise BookNotFoundError(f"Book {book_id} not found")


def update_book(book_id: UUID, *, title: str | None = None, author: str | None = ..., db_url: str | None = None) -> None:
    """Rename. `author=None` clears the author; leaving it out keeps it."""
    sets, params = [], []
    if title and title.strip():
        sets.append("title = %s")
        params.append(title.strip())
    if author is not ...:
        sets.append("author = %s")
        params.append(author.strip() if author and author.strip() else None)
    if sets:
        _update(book_id, ", ".join(sets), tuple(params), db_url)
    else:
        get_book(book_id, db_url=db_url)


def set_last_page(book_id: UUID, page: int, *, db_url: str | None = None) -> None:
    _update(book_id, "last_page = %s", (max(1, page),), db_url)


def mark_opened(book_id: UUID, *, db_url: str | None = None) -> None:
    _update(book_id, "last_opened_at = now()", (), db_url)


def mark_indexing(book_id: UUID, *, db_url: str | None = None) -> None:
    """Before a queued (re)index: the UI shows the book as preparing straight away."""
    _update(book_id, "status = 'indexing', error = NULL", (), db_url)
