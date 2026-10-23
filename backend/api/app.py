"""HTTP API for the frontend's LibraryApi (frontend/src/api/types.ts), plus the built UI.

    /api/...  backend actions, JSON errors as {code, message}
    /         frontend/dist (built by start.sh)
"""
import logging
import shutil
import tempfile
import threading
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal
from uuid import UUID

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import config
import ingest
from chat import AnswerFailedError, BookNotReadyError, ChatUnavailableError, answer_question, chat_available
from embedder import get_embedder
from ingest import BookNotFoundError, DuplicateBookError, NotPdfError
from ingest.library import COVER_NAME

from .events import EventBus
from .jobs import Jobs
from .schemas import book_json, source_json

log = logging.getLogger(__name__)

DIST_DIR = config.PROJECT_ROOT / "frontend" / "dist"

# error -> (HTTP status, code the UI understands, message the UI shows)
ERRORS = {
    NotPdfError: (415, "not_pdf", "This file isn't a PDF. Choose a .pdf file."),
    DuplicateBookError: (409, "duplicate", "This book is already in your library."),
    BookNotFoundError: (404, "not_found", "This book is no longer in your library."),
    BookNotReadyError: (409, "not_ready", "This book is still being prepared."),
    ChatUnavailableError: (503, "unavailable", "Chat is unavailable right now."),
    AnswerFailedError: (502, "failed", "Couldn't get an answer. Try again."),
}


class BookPatch(BaseModel):
    title: str | None = None
    author: str | None = None


class LastPage(BaseModel):
    page: int


class Question(BaseModel):
    question: str


def create_app(
    *,
    db_url: str | None = None,
    books_dir: Path | None = None,
    dist_dir: Path | None = DIST_DIR,
    warm_up: bool = True,
    settings: config.Settings = config.SETTINGS,
) -> FastAPI:
    bus = EventBus()
    jobs = Jobs(bus, db_url=db_url)
    books_dir = Path(books_dir or config.BOOKS_DIR)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        jobs.start()
        for b in ingest.list_books(db_url=db_url):
            if b["status"] == "indexing":  # interrupted by a restart
                jobs.submit(b["id"])
        if warm_up:  # load the model now, not inside the first book's "chunking" stage
            threading.Thread(target=get_embedder, name="embedder-warm-up", daemon=True).start()
        yield
        jobs.stop()

    app = FastAPI(title="Orange Reader", lifespan=lifespan)
    app.state.bus, app.state.jobs = bus, jobs

    for exc, (status, code, message) in ERRORS.items():
        app.add_exception_handler(
            exc, lambda _req, _e, status=status, code=code, message=message: JSONResponse(
                {"code": code, "message": message}, status_code=status
            )
        )

    def book(book_id: UUID) -> dict:
        return book_json(ingest.get_book(book_id, db_url=db_url), jobs.progress(book_id))

    def changed() -> None:
        bus.publish("library", {})

    @app.get("/api/books")
    def list_books(query: str = "", sort: Literal["added", "title", "opened"] = "added"):
        return [book_json(r, jobs.progress(r["id"])) for r in ingest.list_books(query, sort, db_url=db_url)]

    @app.post("/api/books", status_code=201)
    def add_book(file: UploadFile = File(...), title: str = Form(...), author: str | None = Form(None)):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "upload.pdf"
            with open(path, "wb") as f:
                shutil.copyfileobj(file.file, f)
            book_id = ingest.create_book(
                path, title.strip(), (author or "").strip() or None,
                file_name=file.filename, db_url=db_url, books_dir=books_dir,
            )
        jobs.submit(book_id)
        changed()
        return book(book_id)

    @app.post("/api/books/{book_id}/reindex", status_code=204)
    def reindex_book(book_id: UUID):
        ingest.mark_indexing(book_id, db_url=db_url)
        jobs.submit(book_id)
        changed()

    @app.post("/api/books/{book_id}/open")
    def open_book(book_id: UUID):
        ingest.mark_opened(book_id, db_url=db_url)
        changed()
        return book(book_id)

    @app.get("/api/books/{book_id}/file")
    def book_file(book_id: UUID):
        path = Path(ingest.get_book(book_id, db_url=db_url)["file_path"])
        if not path.is_file():
            raise BookNotFoundError(f"PDF for book {book_id} is missing")
        return FileResponse(path, media_type="application/pdf")

    @app.get("/api/books/{book_id}/cover")
    def book_cover(book_id: UUID):
        path = Path(ingest.get_book(book_id, db_url=db_url)["file_path"]).with_name(COVER_NAME)
        if not path.is_file():
            raise BookNotFoundError(f"No cover for book {book_id}")
        return FileResponse(path, media_type="image/jpeg")

    @app.patch("/api/books/{book_id}")
    def update_book(book_id: UUID, patch: BookPatch):
        fields = patch.model_dump(exclude_unset=True)
        ingest.update_book(book_id, db_url=db_url, **fields)
        changed()
        return book(book_id)

    @app.delete("/api/books/{book_id}", status_code=204)
    def delete_book(book_id: UUID):
        ingest.delete_book(book_id, db_url=db_url, books_dir=books_dir)
        bus.publish("deleted", {"bookId": str(book_id)})
        changed()

    @app.put("/api/books/{book_id}/last-page", status_code=204)
    def save_last_page(book_id: UUID, body: LastPage):
        ingest.set_last_page(book_id, body.page, db_url=db_url)

    @app.get("/api/chat/availability")
    def chat_availability():
        return {"availability": "available" if chat_available(settings) else "unavailable"}

    @app.post("/api/books/{book_id}/ask")
    def ask(book_id: UUID, body: Question):
        answer = answer_question(book_id, body.question.strip(), db_url=db_url, settings=settings)
        return {"answer": answer.text, "sources": [source_json(s) for s in answer.sources]}

    @app.get("/api/events")
    async def events(request: Request):
        return StreamingResponse(
            bus.stream(request),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    if dist_dir and Path(dist_dir).is_dir():
        app.mount("/", StaticFiles(directory=dist_dir, html=True), name="ui")
    return app


app = create_app()
