"""CLI for testing without a UI.

    python -m ingest init-db
    python -m ingest add path/to/book.pdf --title "..." [--author "..."]
    python -m ingest reindex <book_id>
    python -m ingest list
    python -m ingest delete <book_id>
"""
import argparse
import logging
import sys
from uuid import UUID

import db

from . import add_book, delete_book, list_books, reindex_book
from .types import IngestError


def print_progress(stage: str, percent: float) -> None:
    print(f"[{percent:5.1f}%] {stage}", flush=True)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="python -m ingest")
    p.add_argument("-v", "--verbose", action="store_true")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init-db", help="apply schema.sql")
    a = sub.add_parser("add", help="add a PDF to the library and index it")
    a.add_argument("pdf")
    a.add_argument("--title", required=True)
    a.add_argument("--author")
    r = sub.add_parser("reindex", help="re-index an existing book")
    r.add_argument("book_id", type=UUID)
    sub.add_parser("list", help="list books")
    d = sub.add_parser("delete", help="delete a book and its chunks")
    d.add_argument("book_id", type=UUID)
    args = p.parse_args(argv)

    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING)
    if not args.verbose:  # the traceback is logged by the pipeline; the CLI prints a one-liner
        logging.getLogger("ingest.pipeline").setLevel(logging.CRITICAL)

    try:
        if args.cmd == "init-db":
            db.apply_schema()
            print("schema applied")
        elif args.cmd == "add":
            book_id = add_book(args.pdf, args.title, args.author, print_progress)
            print(f"book_id {book_id}")
        elif args.cmd == "reindex":
            res = reindex_book(args.book_id, print_progress)
            print(
                f"pages {res.page_count}  chunks {res.chunk_count}  "
                f"empty pages {res.empty_page_count}  {res.duration_s:.1f}s"
            )
        elif args.cmd == "list":
            for b in list_books():
                print(f"{b['id']}  {b['status']:<8} {b['page_count'] or '-':>5}p {b['chunks']:>6}c  {b['title']}"
                      + (f"  ({b['error']})" if b["error"] else ""))
        elif args.cmd == "delete":
            print("deleted" if delete_book(args.book_id) else "not found")
    except (IngestError, FileNotFoundError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
