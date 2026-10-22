import uuid

import pytest

import db
from ingest import (
    DuplicateBookError,
    NoTextLayerError,
    UnreadablePDFError,
    add_book,
    chunk_pages,
    clean_text,
    delete_book,
    extract_pages,
    reindex_book,
)
from stress import make_pdf

pytestmark = pytest.mark.integration


def q(db_url, sql, *args):
    with db.connect(db_url) as conn:
        return conn.execute(sql, args).fetchall()


@pytest.fixture
def books_dir(tmp_path):
    return tmp_path / "books"


def test_ingest_sample_pdf(db_url, books_dir, tmp_path):
    # unique seed so the sha256 never collides with leftovers from earlier runs
    pdf = make_pdf.text_book(tmp_path / "sample.pdf", pages=12, seed=uuid.uuid4().int % 10**6, empty_every=5)
    expected = len(chunk_pages(clean_text(extract_pages(pdf))))

    stages = []
    book_id = add_book(pdf, "Sample", "Tester", lambda s, p: stages.append((s, p)), db_url=db_url, books_dir=books_dir)
    try:
        assert [s for s, _ in stages][:2] == ["extracting", "chunking"]
        assert stages[-1] == ("ready", 100.0)
        assert [p for _, p in stages] == sorted(p for _, p in stages)
        assert (books_dir / str(book_id) / "source.pdf").is_file()

        [(status, pages, model, dim, err)] = q(
            db_url, "SELECT status, page_count, embed_model, embed_dim, error FROM books WHERE id = %s", book_id
        )
        assert (status, pages, dim, err) == ("ready", 12, 1024, None)
        assert model == "Qwen/Qwen3-Embedding-0.6B"

        [(n, n_ord, lo, hi, dims)] = q(
            db_url,
            "SELECT count(*), count(DISTINCT ordinal), min(ordinal), max(ordinal),"
            " min(vector_dims(embedding)) FROM chunks WHERE book_id = %s",
            book_id,
        )
        assert n == expected > 0
        assert (n_ord, lo, hi, dims) == (n, 0, n - 1, 1024)

        # unit-norm vectors
        [(norm,)] = q(db_url, "SELECT min(vector_norm(embedding)) FROM chunks WHERE book_id = %s", book_id)
        assert abs(norm - 1) < 1e-2

        # re-index replaces, never duplicates
        res = reindex_book(book_id, db_url=db_url)
        assert res.chunk_count == expected
        assert res.empty_page_count == 2
        assert q(db_url, "SELECT count(*) FROM chunks WHERE book_id = %s", book_id)[0][0] == expected

        with pytest.raises(DuplicateBookError):
            add_book(pdf, "Again", db_url=db_url, books_dir=books_dir)
    finally:
        assert delete_book(book_id, db_url=db_url, books_dir=books_dir)
    assert q(db_url, "SELECT count(*) FROM chunks WHERE book_id = %s", book_id)[0][0] == 0
    assert not (books_dir / str(book_id)).exists()


@pytest.mark.parametrize(
    "kind,error,message",
    [
        ("scanned", NoTextLayerError, "No text layer (scanned PDF)"),
        ("encrypted", UnreadablePDFError, "PDF is password-protected"),
        ("corrupt", UnreadablePDFError, "Cannot open PDF"),
    ],
)
def test_failures_mark_book_failed(db_url, books_dir, tmp_path, kind, error, message):
    pdf = tmp_path / f"{kind}.pdf"
    {"scanned": make_pdf.scanned_book, "encrypted": make_pdf.encrypted_book, "corrupt": make_pdf.corrupt_file}[kind](pdf)
    # make the file unique so repeated runs don't hit the duplicate check
    with open(pdf, "ab") as f:
        f.write(f"\n%{uuid.uuid4()}\n".encode())

    stages = []
    with pytest.raises(error):
        add_book(pdf, kind, on_progress=lambda s, p: stages.append(s), db_url=db_url, books_dir=books_dir)
    assert stages[-1] == "failed"
    [(book_id, status, err)] = q(db_url, "SELECT id, status, error FROM books WHERE title = %s ORDER BY created_at DESC LIMIT 1", kind)
    try:
        assert status == "failed"
        assert err.startswith(message)
        assert q(db_url, "SELECT count(*) FROM chunks WHERE book_id = %s", book_id)[0][0] == 0
    finally:
        delete_book(book_id, db_url=db_url, books_dir=books_dir)
