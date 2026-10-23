"""Background (re)indexing: one worker thread, so add_book never blocks a request.

One worker is enough: the embedder serialises GPU work behind a lock anyway.
"""
import logging
import queue
import threading
from dataclasses import asdict, dataclass
from uuid import UUID

from ingest import BookNotFoundError, reindex_book
from ingest.pipeline import _short_error

from .events import EventBus

log = logging.getLogger(__name__)

STAGES = ("extracting", "chunking", "embedding", "saving")


@dataclass
class Progress:
    percent: int
    status: str  # indexing | ready | failed
    stage: str | None
    error: str | None


class Jobs:
    def __init__(self, bus: EventBus, *, db_url: str | None = None):
        self._bus = bus
        self._db_url = db_url
        self._queue: queue.Queue = queue.Queue()
        self._lock = threading.Lock()
        self._pending: set[UUID] = set()  # queued or running
        self._progress: dict[UUID, Progress] = {}
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="ingest-worker", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        self._queue.put(None)
        if self._thread:
            self._thread.join(timeout)

    def submit(self, book_id: UUID) -> None:
        """Queue a (re)index. A book already queued or running is not queued twice."""
        with self._lock:
            if book_id in self._pending:
                return
            self._pending.add(book_id)
        self._set(book_id, Progress(0, "indexing", "extracting", None))
        self._queue.put(book_id)

    def progress(self, book_id: UUID) -> Progress | None:
        with self._lock:
            return self._progress.get(book_id)

    def _set(self, book_id: UUID, p: Progress) -> None:
        with self._lock:
            self._progress[book_id] = p
        self._bus.publish("progress", {"bookId": str(book_id), **asdict(p)})

    def _run(self) -> None:
        while (book_id := self._queue.get()) is not None:
            def on_progress(stage: str, pct: float, book_id=book_id):
                if stage in STAGES:
                    self._set(book_id, Progress(int(pct), "indexing", stage, None))

            try:
                reindex_book(book_id, on_progress, db_url=self._db_url)
                final = Progress(100, "ready", None, None)
            except BookNotFoundError:
                final = None  # deleted while queued or running
            except Exception as e:  # the pipeline already marked the row failed
                last = self.progress(book_id)
                final = Progress(last.percent if last else 0, "failed", None, _short_error(e))
            with self._lock:
                self._pending.discard(book_id)
            if final:
                self._set(book_id, final)
            with self._lock:  # the database is the source of truth again
                self._progress.pop(book_id, None)
            self._bus.publish("library", {})
