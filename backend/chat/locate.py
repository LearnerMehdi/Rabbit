"""Where an excerpt sits on its pages: one rectangle per line of PDF text it covers.

Chunks are stored as cleaned text (ingest/clean.py only drops whitespace and line-break
hyphens), so the letters and digits of a chunk, in order, appear verbatim in the letters
and digits of its pages' words. Matching on that stream finds the exact words; if it ever
doesn't (text extracted differently), a word-level diff marks the longest matching runs.
"""
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path

import pymupdf as fitz

# a fallback match must cover this many words in a row, so stray common words don't light up
MIN_RUN = 4


@dataclass
class Highlight:
    page: int  # 1-based
    # (x0, y0, x1, y1) as fractions of the page's width and height, origin top-left
    rects: list[tuple[float, float, float, float]]


@dataclass
class _Word:
    page: int
    line: tuple[int, int]  # (block, line) on its page
    box: fitz.Rect
    key: str  # lowercased letters and digits


def _key(text: str) -> str:
    return "".join(c for c in text.lower() if c.isalnum())


class PageWords:
    """Words of a book's pages, read once per page."""

    def __init__(self, pdf_path: Path):
        self.doc = fitz.open(pdf_path)
        self._pages: dict[int, tuple[list[_Word], fitz.Rect]] = {}

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.doc.close()

    def page(self, n: int) -> tuple[list[_Word], fitz.Rect]:
        if n not in self._pages:
            page = self.doc[n - 1]
            m = page.rotation_matrix
            words = [
                _Word(n, (b, ln), fitz.Rect(x0, y0, x1, y1) * m, _key(text))
                for x0, y0, x1, y1, text, b, ln, _ in page.get_text("words")
            ]
            self._pages[n] = ([w for w in words if w.key], page.rect)
        return self._pages[n]


def _exact(words: list[_Word], content: str) -> list[_Word]:
    """The words whose letters/digits contain the content's letters/digits exactly."""
    needle = _key(content)
    if not needle:
        return []
    stream, owner = [], []
    for i, w in enumerate(words):
        stream.append(w.key)
        owner.extend([i] * len(w.key))
    at = "".join(stream).find(needle)
    if at < 0:
        return []
    return words[owner[at] : owner[at + len(needle) - 1] + 1]


def _fuzzy(words: list[_Word], content: str) -> list[_Word]:
    """Words in runs of at least MIN_RUN that match the content word for word."""
    target = [k for k in map(_key, content.split()) if k]
    sm = SequenceMatcher(None, [w.key for w in words], target, autojunk=False)
    out = []
    for a, _, size in sm.get_matching_blocks():
        if size >= MIN_RUN:
            out.extend(words[a : a + size])
    return out


def locate(pages: PageWords, page_start: int, page_end: int, content: str) -> list[Highlight]:
    """Line rectangles of `content` on pages page_start..page_end (empty if not found)."""
    words, sizes = [], {}
    for n in range(page_start, page_end + 1):
        if 1 <= n <= pages.doc.page_count:
            page_words, sizes[n] = pages.page(n)
            words.extend(page_words)
    hit = _exact(words, content) or _fuzzy(words, content)

    lines: dict[tuple[int, tuple[int, int]], fitz.Rect] = {}
    for w in hit:
        k = (w.page, w.line)
        lines[k] = lines[k] | w.box if k in lines else fitz.Rect(w.box)
    out: dict[int, Highlight] = {}
    for (n, _), r in lines.items():
        size = sizes[n]
        out.setdefault(n, Highlight(n, [])).rects.append(
            (r.x0 / size.width, r.y0 / size.height, r.x1 / size.width, r.y1 / size.height)
        )
    return [out[n] for n in sorted(out)]
