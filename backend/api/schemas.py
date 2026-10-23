"""Database rows -> the frontend's `Book` (frontend/src/api/types.ts)."""
from datetime import datetime
from pathlib import Path

from ingest.library import COVER_NAME

from .jobs import Progress


def _ms(t: datetime | None) -> int | None:
    return int(t.timestamp() * 1000) if t else None


def book_json(row: dict, progress: Progress | None = None) -> dict:
    status = progress.status if progress else row["status"]
    if progress:
        percent, stage, error = progress.percent, progress.stage, progress.error
    else:
        percent, stage, error = (100 if status == "ready" else 0), None, row["error"]
        if status == "indexing":
            stage = "extracting"
    has_cover = (Path(row["file_path"]).parent / COVER_NAME).is_file()
    return {
        "id": str(row["id"]),
        "title": row["title"],
        "author": row["author"],
        "fileName": row["file_name"] or Path(row["file_path"]).name,
        "fileSize": row["file_size"] or 0,
        "pageCount": row["page_count"],
        "status": status,
        "percent": percent,
        "stage": stage,
        "error": error if status == "failed" else None,
        "createdAt": _ms(row["created_at"]),
        "lastOpenedAt": _ms(row["last_opened_at"]),
        "lastPage": row["last_page"],
        "cover": f"/api/books/{row['id']}/cover" if has_cover else None,
    }

