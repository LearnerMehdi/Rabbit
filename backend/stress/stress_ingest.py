"""Stress tests for the ingestion pipeline (no API; calls the library directly).

Runs against a separate database (orange_rabbit_stress by default) and a
separate books directory, so the real library is never touched.

    python -m stress.stress_ingest                      # all scenarios
    python -m stress.stress_ingest throughput --books 3 --pages 300
    python -m stress.stress_ingest concurrent --workers 4
    python -m stress.stress_ingest reindex --runs 5
    python -m stress.stress_ingest failures
    python -m stress.stress_ingest large --pages 1500

Exit code is 1 if any check fails. A JSON report is written to stress/out/.
"""
import argparse
import json
import logging
import shutil
import sys
import threading
import time
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from pathlib import Path

import db
from embedder import get_embedder
from ingest import (
    BookNotFoundError,
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

from . import make_pdf

OUT = Path(__file__).resolve().parent / "out"
DEFAULT_DB = "postgresql://rabbit:rabbit@localhost:5432/orange_rabbit_stress"


@dataclass
class Check:
    name: str
    ok: bool
    detail: str = ""


@dataclass
class Scenario:
    name: str
    checks: list[Check] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)
    seconds: float = 0.0

    def check(self, name: str, ok: bool, detail: str = "") -> bool:
        self.checks.append(Check(name, bool(ok), detail))
        mark = "PASS" if ok else "FAIL"
        print(f"    [{mark}] {name}" + (f" — {detail}" if detail else ""), flush=True)
        return ok

    @property
    def ok(self) -> bool:
        return all(c.ok for c in self.checks)


class StageTimer:
    """on_progress callback that records when each stage started."""

    def __init__(self, label: str = "", echo: bool = False):
        self.label, self.echo = label, echo
        self.t0 = time.perf_counter()
        self.starts: dict[str, float] = {}
        self.last = None

    def __call__(self, stage: str, percent: float):
        if stage not in self.starts:
            self.starts[stage] = time.perf_counter() - self.t0
        if self.echo and (stage, int(percent) // 10) != self.last:
            self.last = (stage, int(percent) // 10)
            print(f"      {self.label}[{percent:5.1f}%] {stage}", flush=True)

    def durations(self) -> dict[str, float]:
        order = sorted(self.starts.items(), key=lambda kv: kv[1])
        out = {}
        for (stage, t), nxt in zip(order, order[1:] + [(None, time.perf_counter() - self.t0)]):
            out[stage] = round(nxt[1] - t, 3)
        return out


class Ctx:
    def __init__(self, db_url: str, work: Path):
        self.db_url = db_url
        self.work = work
        self.books_dir = work / "books"
        self.pdf_dir = work / "pdfs"
        self.pdf_dir.mkdir(parents=True, exist_ok=True)
        self.created: list[uuid.UUID] = []
        self._lock = threading.Lock()

    def pdf(self, pages: int, tag: str) -> Path:
        # random seed: content (and sha256) unique per run
        seed = uuid.uuid4().int % 10**9
        return make_pdf.text_book(self.pdf_dir / f"{tag}-{seed}.pdf", pages, seed=seed, empty_every=37)

    def add(self, pdf: Path, title: str, on_progress=None) -> uuid.UUID:
        book_id = add_book(pdf, title, "stress", on_progress, db_url=self.db_url, books_dir=self.books_dir)
        with self._lock:
            self.created.append(book_id)
        return book_id

    def reindex(self, book_id, on_progress=None):
        return reindex_book(book_id, on_progress, db_url=self.db_url)

    def q(self, sql: str, *args):
        with db.connect(self.db_url) as conn:
            return conn.execute(sql, args).fetchall()

    def integrity(self, book_id) -> dict:
        [(n, n_ord, lo, hi, dims, bad_pages, empty)] = self.q(
            "SELECT count(*), count(DISTINCT ordinal), min(ordinal), max(ordinal),"
            " count(DISTINCT vector_dims(embedding)),"
            " count(*) FILTER (WHERE page_start > page_end OR page_start < 1),"
            " count(*) FILTER (WHERE length(content) = 0)"
            " FROM chunks WHERE book_id = %s",
            book_id,
        )
        [(status, page_count, err)] = self.q("SELECT status, page_count, error FROM books WHERE id = %s", book_id)
        ok = (
            status == "ready"
            and n > 0
            and n == n_ord
            and (lo, hi) == (0, n - 1)
            and dims == 1
            and bad_pages == 0
            and empty == 0
        )
        return {"ok": ok, "chunks": n, "status": status, "pages": page_count, "error": err,
                "distinct_ordinals": n_ord, "ordinal_range": (lo, hi)}

    def cleanup(self):
        for book_id in self.created:
            delete_book(book_id, db_url=self.db_url, books_dir=self.books_dir)
        self.created.clear()


def expected_chunks(pdf: Path) -> int:
    return len(chunk_pages(clean_text(extract_pages(pdf))))


def gpu_peak_gb() -> float | None:
    try:
        import torch

        return round(torch.cuda.max_memory_allocated() / 1e9, 2) if torch.cuda.is_available() else None
    except Exception:
        return None


# --- scenarios -----------------------------------------------------------------


def sc_throughput(ctx: Ctx, s: Scenario, args):
    """Sequential ingestion of N books; per-stage timings and throughput."""
    rows = []
    for i in range(args.books):
        pdf = ctx.pdf(args.pages, f"tp{i}")
        exp = expected_chunks(pdf)
        timer = StageTimer(f"book {i + 1}/{args.books} ", echo=True)
        t = time.perf_counter()
        book_id = ctx.add(pdf, f"[stress] throughput {i}", timer)
        dt = time.perf_counter() - t
        info = ctx.integrity(book_id)
        s.check(f"book {i} integrity", info["ok"] and info["chunks"] == exp,
                f"{info['chunks']} chunks (expected {exp}), {dt:.1f}s")
        rows.append({"seconds": round(dt, 2), "chunks": info["chunks"], "stages": timer.durations()})
    total_s = sum(r["seconds"] for r in rows)
    total_chunks = sum(r["chunks"] for r in rows)
    s.metrics.update(
        books=rows,
        pages_per_s=round(args.books * args.pages / total_s, 1),
        chunks_per_s=round(total_chunks / total_s, 1),
        first_book_s=rows[0]["seconds"],
        warm_book_s=round(sum(r["seconds"] for r in rows[1:]) / max(1, len(rows) - 1), 2) if len(rows) > 1 else None,
    )
    print(f"    {s.metrics['pages_per_s']} pages/s, {s.metrics['chunks_per_s']} chunks/s; "
          f"stages of last book: {rows[-1]['stages']}")


def sc_reindex(ctx: Ctx, s: Scenario, args):
    """Re-index the same book repeatedly: same chunk count, no duplicates."""
    pdf = ctx.pdf(args.pages, "ri")
    book_id = ctx.add(pdf, "[stress] reindex")
    first = ctx.integrity(book_id)["chunks"]
    [(first_ids_max,)] = ctx.q("SELECT max(id) FROM chunks WHERE book_id = %s", book_id)
    times = []
    for r in range(args.runs):
        res = ctx.reindex(book_id)
        info = ctx.integrity(book_id)
        times.append(round(res.duration_s, 2))
        s.check(f"reindex {r + 1}/{args.runs}", info["ok"] and info["chunks"] == res.chunk_count == first,
                f"{info['chunks']} chunks, {res.duration_s:.1f}s")
    [(min_id,)] = ctx.q("SELECT min(id) FROM chunks WHERE book_id = %s", book_id)
    s.check("old chunk rows replaced", min_id > first_ids_max)
    s.metrics.update(chunks=first, reindex_seconds=times)


def sc_concurrent(ctx: Ctx, s: Scenario, args):
    """Parallel adds of distinct books, parallel reindex of one book, racing duplicate adds."""
    pdfs = [ctx.pdf(args.pages // 2, f"cc{i}") for i in range(args.workers)]
    expected = {p: expected_chunks(p) for p in pdfs}

    t = time.perf_counter()
    errors = []

    def add(p):
        try:
            return p, ctx.add(p, f"[stress] concurrent {p.stem}")
        except Exception as e:
            errors.append(f"{p.name}: {e!r}")
            return p, None

    with ThreadPoolExecutor(args.workers) as ex:
        results = list(ex.map(add, pdfs))
    dt = time.perf_counter() - t
    s.check(f"{args.workers} parallel adds without error", not errors, "; ".join(errors)[:300])
    for p, book_id in results:
        if book_id:
            info = ctx.integrity(book_id)
            s.check(f"{p.stem} integrity", info["ok"] and info["chunks"] == expected[p],
                    f"{info['chunks']} chunks (expected {expected[p]})")
    s.metrics["parallel_add_s"] = round(dt, 2)

    # same book re-indexed from several threads at once
    target = next((b for _, b in results if b), None)
    if target:
        exp = ctx.integrity(target)["chunks"]
        errs = []

        def reidx(_):
            try:
                ctx.reindex(target)
            except Exception as e:
                errs.append(repr(e))

        with ThreadPoolExecutor(args.workers) as ex:
            list(ex.map(reidx, range(args.workers)))
        info = ctx.integrity(target)
        s.check(f"{args.workers} simultaneous reindexes of one book", not errs and info["ok"] and info["chunks"] == exp,
                f"{info['chunks']} chunks (expected {exp}) {'; '.join(errs)[:200]}")

    # identical file added from several threads: exactly one wins
    dup = ctx.pdf(5, "dup")
    outcomes = []

    def add_dup(_):
        try:
            outcomes.append(("ok", ctx.add(dup, "[stress] dup race")))
        except DuplicateBookError:
            outcomes.append(("dup", None))
        except Exception as e:
            outcomes.append(("err", repr(e)))

    with ThreadPoolExecutor(args.workers) as ex:
        list(ex.map(add_dup, range(args.workers)))
    kinds = sorted(k for k, _ in outcomes)
    s.check("duplicate race: one added, rest rejected", kinds == ["dup"] * (args.workers - 1) + ["ok"], str(kinds))


def sc_failures(ctx: Ctx, s: Scenario, args):
    """Bad inputs end as status 'failed' with a clear error and no chunks."""
    cases = [
        ("scanned", make_pdf.scanned_book, NoTextLayerError, "No text layer (scanned PDF)"),
        ("encrypted", make_pdf.encrypted_book, UnreadablePDFError, "PDF is password-protected"),
        ("corrupt", make_pdf.corrupt_file, UnreadablePDFError, "Cannot open PDF"),
    ]
    for name, make, exc, msg in cases:
        pdf = ctx.pdf_dir / f"{name}-{uuid.uuid4().hex[:8]}.pdf"
        make(pdf)
        with open(pdf, "ab") as f:  # unique bytes -> unique sha256
            f.write(f"\n%{uuid.uuid4()}\n".encode())
        stages = []
        title = f"[stress] {name} {pdf.stem}"
        try:
            ctx.add(pdf, title, lambda st, p: stages.append(st))
            raised = None
        except Exception as e:
            raised = e
        rows = ctx.q("SELECT id, status, error FROM books WHERE title = %s", title)
        if rows:
            ctx.created.append(rows[0][0])
        ok = (
            isinstance(raised, exc)
            and stages[-1:] == ["failed"]
            and rows and rows[0][1] == "failed" and (rows[0][2] or "").startswith(msg)
            and ctx.q("SELECT count(*) FROM chunks WHERE book_id = %s", rows[0][0])[0][0] == 0
        )
        s.check(f"{name} -> failed", ok, f"{type(raised).__name__}: {rows[0][2] if rows else 'no row'}")

    good = ctx.pdf(3, "dupcheck")
    ctx.add(good, "[stress] dupcheck")
    try:
        ctx.add(good, "[stress] dupcheck again")
        s.check("duplicate rejected", False, "second add succeeded")
    except DuplicateBookError as e:
        s.check("duplicate rejected", True, str(e))

    try:
        ctx.add(ctx.pdf_dir / "does-not-exist.pdf", "[stress] missing")
        s.check("missing file rejected", False)
    except FileNotFoundError:
        s.check("missing file rejected", True)

    try:
        ctx.reindex(uuid.uuid4())
        s.check("reindex unknown book rejected", False)
    except BookNotFoundError:
        s.check("reindex unknown book rejected", True)

    # a book whose source file vanished: reindex fails cleanly, then recovers when restored
    book_id = ctx.add(ctx.pdf(3, "vanish"), "[stress] vanish")
    src = ctx.books_dir / str(book_id) / "source.pdf"
    backup = src.with_suffix(".bak")
    src.rename(backup)
    try:
        ctx.reindex(book_id)
        s.check("reindex with missing source -> failed", False)
    except UnreadablePDFError:
        [(status,)] = ctx.q("SELECT status FROM books WHERE id = %s", book_id)
        s.check("reindex with missing source -> failed", status == "failed", status)
    backup.rename(src)
    ctx.reindex(book_id)
    s.check("failed book recovers on reindex", ctx.integrity(book_id)["ok"])


def sc_large(ctx: Ctx, s: Scenario, args):
    """One very long book: time and memory scaling."""
    pages = args.large_pages
    pdf = ctx.pdf(pages, "large")
    timer = StageTimer("large ", echo=True)
    t = time.perf_counter()
    book_id = ctx.add(pdf, f"[stress] large {pages}p", timer)
    dt = time.perf_counter() - t
    info = ctx.integrity(book_id)
    s.check(f"{pages}-page book integrity", info["ok"], f"{info['chunks']} chunks, {dt:.1f}s")
    s.metrics.update(pages=pages, seconds=round(dt, 2), chunks=info["chunks"], stages=timer.durations())


def sc_cascade(ctx: Ctx, s: Scenario, args):
    """Deleting every book created in this run removes all its chunks and files."""
    ids = list(ctx.created)
    for book_id in ids:
        delete_book(book_id, db_url=ctx.db_url, books_dir=ctx.books_dir)
    left = ctx.q("SELECT count(*) FROM chunks WHERE book_id = ANY(%s)", ids)[0][0] if ids else 0
    rows = ctx.q("SELECT count(*) FROM books WHERE id = ANY(%s)", ids)[0][0] if ids else 0
    files = [p for p in ids if (ctx.books_dir / str(p)).exists()]
    s.check(f"delete {len(ids)} books cascades to chunks", left == 0 and rows == 0, f"{rows} books, {left} chunks left")
    s.check("stored files removed", not files)
    ctx.created.clear()


SCENARIOS = {
    "throughput": sc_throughput,
    "reindex": sc_reindex,
    "concurrent": sc_concurrent,
    "failures": sc_failures,
    "large": sc_large,
}


def main() -> int:
    p = argparse.ArgumentParser(prog="python -m stress.stress_ingest")
    p.add_argument("scenarios", nargs="*", metavar="scenario", help=f"{', '.join(SCENARIOS)} or all (default)")
    p.add_argument("--db-url", default=DEFAULT_DB)
    p.add_argument("--books", type=int, default=3, help="throughput: number of books")
    p.add_argument("--pages", type=int, default=250, help="pages per synthetic book")
    p.add_argument("--large-pages", type=int, default=1200)
    p.add_argument("--runs", type=int, default=5, help="reindex: repetitions")
    p.add_argument("--workers", type=int, default=4, help="concurrent: threads")
    p.add_argument("--keep", action="store_true", help="keep books in the stress DB (skips cascade check)")
    args = p.parse_args()
    names = list(SCENARIOS) if not args.scenarios or "all" in args.scenarios else args.scenarios
    if unknown := set(names) - set(SCENARIOS):
        p.error(f"unknown scenario(s): {', '.join(sorted(unknown))}")

    logging.basicConfig(level=logging.WARNING)
    logging.getLogger("ingest.pipeline").setLevel(logging.CRITICAL)  # expected failures log tracebacks

    db.ensure_database(args.db_url)
    work = OUT / f"run-{time.strftime('%Y%m%d-%H%M%S')}"
    ctx = Ctx(args.db_url, work)

    print(f"stress DB {args.db_url}\nwork dir  {work}")
    t = time.perf_counter()
    get_embedder()  # load once up front so the first scenario isn't charged for it
    print(f"model loaded in {time.perf_counter() - t:.1f}s\n")

    results: list[Scenario] = []
    for name in names + ([] if args.keep else ["cascade"]):
        s = Scenario(name)
        print(f"== {name}: {(SCENARIOS.get(name) or sc_cascade).__doc__.strip().splitlines()[0]}")
        t = time.perf_counter()
        try:
            (SCENARIOS.get(name) or sc_cascade)(ctx, s, args)
        except Exception as e:
            s.check("scenario ran", False, f"{type(e).__name__}: {e}")
            traceback.print_exc()
        s.seconds = round(time.perf_counter() - t, 2)
        results.append(s)
        print(f"   {'ok' if s.ok else 'FAILED'} in {s.seconds}s\n")

    if not args.keep:
        ctx.cleanup()
        shutil.rmtree(work, ignore_errors=True)

    report = {
        "args": vars(args),
        "gpu_peak_gb": gpu_peak_gb(),
        "scenarios": [asdict(s) | {"ok": s.ok} for s in results],
    }
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"report-{time.strftime('%Y%m%d-%H%M%S')}.json"
    path.write_text(json.dumps(report, indent=2, default=str))

    print("summary")
    for s in results:
        n_fail = sum(not c.ok for c in s.checks)
        print(f"  {'ok  ' if s.ok else 'FAIL'} {s.name:<11} {len(s.checks) - n_fail}/{len(s.checks)} checks  {s.seconds:>7.1f}s")
    print(f"  GPU peak {report['gpu_peak_gb']} GB\nreport {path}")
    return 0 if all(s.ok for s in results) else 1


if __name__ == "__main__":
    sys.exit(main())
