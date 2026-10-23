"""Adding a book through the HTTP API and everything it triggers:
create_book (row, source.pdf, cover.jpg) -> background job -> ingest_book stages -> ready."""
import time
import uuid

import pytest
from fastapi.testclient import TestClient

import db
from api.app import create_app
from ingest import chunk_pages, clean_text, create_book, delete_book, extract_pages
from stress import make_pdf

pytestmark = pytest.mark.integration


def q(db_url, sql, *args):
    with db.connect(db_url) as conn:
        return conn.execute(sql, args).fetchall()


@pytest.fixture
def books_dir(tmp_path):
    return tmp_path / "books"


@pytest.fixture
def app(db_url, books_dir):
    return create_app(db_url=db_url, books_dir=books_dir, dist_dir=None, warm_up=False)


@pytest.fixture
def events(app):
    seen = []
    app.state.bus.subscribe(lambda e, d: seen.append((e, d)))
    return seen


def unique_book(tmp_path, name="book.pdf", pages=8):
    return make_pdf.text_book(tmp_path / name, pages=pages, seed=uuid.uuid4().int % 10**6)


def upload(client, path, title="A book", author="Ann Author", name=None):
    with open(path, "rb") as f:
        return client.post(
            "/api/books",
            files={"file": (name or path.name, f, "application/pdf")},
            data={"title": title, "author": author},
        )


def wait_done(events, book_id, timeout=180):
    """Progress events for one book, until it is ready or failed."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        mine = [d for e, d in events if e == "progress" and d["bookId"] == book_id]
        if mine and mine[-1]["status"] in ("ready", "failed"):
            return mine
        time.sleep(0.1)
    raise TimeoutError(f"book {book_id} not done after {timeout}s")


def test_add_book_runs_the_whole_pipeline(app, events, db_url, books_dir, tmp_path):
    pdf = unique_book(tmp_path)
    with TestClient(app) as client:
        r = upload(client, pdf, title="Sample", author="Tester", name="Sample Book.pdf")
        assert r.status_code == 201
        book = r.json()
        book_id = book["id"]
        try:
            # create_book: row + stored copy + cover, before any indexing
            assert book["status"] == "indexing" and book["percent"] == 0
            assert (book["title"], book["author"], book["fileName"]) == ("Sample", "Tester", "Sample Book.pdf")
            assert book["fileSize"] == pdf.stat().st_size
            assert (books_dir / book_id / "source.pdf").read_bytes() == pdf.read_bytes()
            assert (books_dir / book_id / "cover.jpg").is_file()
            assert book["cover"] == f"/api/books/{book_id}/cover"
            assert ("library", {}) in events

            # the job: every stage in order, increasing percent, then ready
            progress = wait_done(events, book_id)
            assert progress[-1] == {"bookId": book_id, "percent": 100, "status": "ready", "stage": None, "error": None}
            stages = [p["stage"] for p in progress[:-1]]
            assert [s for i, s in enumerate(stages) if i == 0 or s != stages[i - 1]] == [
                "extracting", "chunking", "embedding", "saving",
            ]
            percents = [p["percent"] for p in progress]
            assert percents == sorted(percents)

            # what ingest_book stored
            expected = chunk_pages(clean_text(extract_pages(pdf)))
            [(n, pages)] = q(db_url, "SELECT count(*), max(page_end) FROM chunks WHERE book_id = %s", uuid.UUID(book_id))
            assert n == len(expected)
            [(status, page_count, model, dim)] = q(
                db_url, "SELECT status, page_count, embed_model, embed_dim FROM books WHERE id = %s", uuid.UUID(book_id)
            )
            assert (status, page_count, dim) == ("ready", 8, 1024)
            assert model == "Qwen/Qwen3-Embedding-0.6B"

            listed = {b["id"]: b for b in client.get("/api/books").json()}
            assert listed[book_id]["status"] == "ready" and listed[book_id]["pageCount"] == 8
        finally:
            client.delete(f"/api/books/{book_id}")


def test_rejections(app, db_url, tmp_path):
    not_pdf = tmp_path / "notes.pdf"
    not_pdf.write_text("just text, renamed to .pdf")
    with TestClient(app) as client:
        before = q(db_url, "SELECT count(*) FROM books")[0][0]
        r = upload(client, not_pdf)
        assert (r.status_code, r.json()["code"]) == (415, "not_pdf")
        assert r.json()["message"] == "This file isn't a PDF. Choose a .pdf file."
        assert q(db_url, "SELECT count(*) FROM books")[0][0] == before  # no row created

        pdf = unique_book(tmp_path)
        first = upload(client, pdf).json()["id"]
        try:
            r = upload(client, pdf, title="Same file again")
            assert (r.status_code, r.json()["code"]) == (409, "duplicate")
            assert r.json()["message"] == "This book is already in your library."
        finally:
            client.delete(f"/api/books/{first}")

        r = client.post(f"/api/books/{uuid.uuid4()}/open")
        assert (r.status_code, r.json()["code"]) == (404, "not_found")


def test_scanned_pdf_fails_with_a_reason(app, events, tmp_path):
    pdf = make_pdf.scanned_book(tmp_path / "scan.pdf")
    with open(pdf, "ab") as f:
        f.write(f"\n%{uuid.uuid4()}\n".encode())
    with TestClient(app) as client:
        book_id = upload(client, pdf).json()["id"]
        try:
            final = wait_done(events, book_id)[-1]
            assert (final["status"], final["error"]) == ("failed", "No text layer (scanned PDF)")
            [book] = [b for b in client.get("/api/books").json() if b["id"] == book_id]
            assert (book["status"], book["error"]) == ("failed", "No text layer (scanned PDF)")
        finally:
            client.delete(f"/api/books/{book_id}")


def test_book_actions(app, events, db_url, books_dir, tmp_path):
    pdf = unique_book(tmp_path, pages=4)
    with TestClient(app) as client:
        book_id = upload(client, pdf, title="Old title").json()["id"]
        try:
            wait_done(events, book_id)
            old_chunks = q(db_url, "SELECT min(id) FROM chunks WHERE book_id = %s", uuid.UUID(book_id))[0][0]

            r = client.patch(f"/api/books/{book_id}", json={"title": "New title"})
            assert (r.json()["title"], r.json()["author"]) == ("New title", "Ann Author")
            assert client.patch(f"/api/books/{book_id}", json={"author": None}).json()["author"] is None

            assert client.put(f"/api/books/{book_id}/last-page", json={"page": 3}).status_code == 204
            opened = client.post(f"/api/books/{book_id}/open").json()
            assert opened["lastPage"] == 3 and opened["lastOpenedAt"]
            assert client.get(f"/api/books/{book_id}/file").content == pdf.read_bytes()
            cover = client.get(f"/api/books/{book_id}/cover")
            assert cover.headers["content-type"] == "image/jpeg" and cover.content[:2] == b"\xff\xd8"

            assert [b["id"] for b in client.get("/api/books", params={"query": "new tit"}).json()] == [book_id]
            assert client.get("/api/books", params={"query": "no such book"}).json() == []

            events.clear()
            assert client.post(f"/api/books/{book_id}/reindex").status_code == 204
            assert wait_done(events, book_id)[-1]["status"] == "ready"
            assert q(db_url, "SELECT min(id) FROM chunks WHERE book_id = %s", uuid.UUID(book_id))[0][0] > old_chunks

            assert client.delete(f"/api/books/{book_id}").status_code == 204
            assert q(db_url, "SELECT count(*) FROM chunks WHERE book_id = %s", uuid.UUID(book_id))[0][0] == 0
            assert not (books_dir / book_id).exists()
            assert ("deleted", {"bookId": book_id}) in events
        finally:
            delete_book(uuid.UUID(book_id), db_url=db_url, books_dir=books_dir)


def test_interrupted_book_resumes_on_start(app, events, db_url, books_dir, tmp_path):
    # a row left 'indexing' by a server that stopped mid-way
    book_id = create_book(unique_book(tmp_path, pages=3), "Interrupted", db_url=db_url, books_dir=books_dir)
    try:
        with TestClient(app):
            assert wait_done(events, str(book_id))[-1]["status"] == "ready"
    finally:
        delete_book(book_id, db_url=db_url, books_dir=books_dir)
