"""Synthetic PDFs for tests and stress runs.

    python -m stress.make_pdf book out.pdf --pages 250 [--seed 1]
    python -m stress.make_pdf scanned|encrypted|corrupt out.pdf
"""
import argparse
import random
from pathlib import Path

import pymupdf as fitz

WORDS = (
    "the of and to in is that for it as with was on be by this are from at or an which "
    "diffusion model gradient energy system matrix vector particle boundary condition "
    "equation temperature distribution probability network learning representation "
    "observation experiment analysis structure function measurement convergence "
    "approximation transformation interpretation characteristic"
).split()

LINE_CHARS = 85
LINES_PER_PAGE = 52
FONT = 10
LEADING = 13


def _sentence(rng: random.Random) -> str:
    words = [rng.choice(WORDS) for _ in range(rng.randint(6, 24))]
    return " ".join(words).capitalize() + rng.choice([".", ".", ".", "?", "!"])


def _paragraph(rng: random.Random) -> str:
    return " ".join(_sentence(rng) for _ in range(rng.randint(2, 9)))


def _wrap(text: str, rng: random.Random) -> list[str]:
    """Greedy wrap; sometimes hyphenates a long word across the line end."""
    lines, cur = [], ""
    for word in text.split():
        if len(cur) + 1 + len(word) <= LINE_CHARS:
            cur = f"{cur} {word}" if cur else word
            continue
        room = LINE_CHARS - len(cur) - 2
        if len(word) >= 8 and room >= 3 and rng.random() < 0.5:
            cut = min(room, len(word) - 3)
            lines.append(f"{cur} {word[:cut]}-")
            cur = word[cut:]
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def book_lines(pages: int, seed: int = 0, empty_every: int = 0) -> list[list[str]]:
    """Text lines per page; a blank line separates paragraphs."""
    rng = random.Random(seed)
    out = []
    for n in range(1, pages + 1):
        if empty_every and n % empty_every == 0:
            out.append([])
            continue
        lines = []
        while len(lines) < LINES_PER_PAGE:
            lines.extend(_wrap(_paragraph(rng), rng))
            lines.append("")
        out.append(lines[:LINES_PER_PAGE])
    return out


def write_pages(path: Path, page_lines: list[list[str]]) -> Path:
    doc = fitz.open()
    for lines in page_lines:
        page = doc.new_page()
        y = 50
        for line in lines:
            if line:
                page.insert_text((50, y), line, fontsize=FONT)
            y += LEADING
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(path)
    doc.close()
    return path


def text_book(path: Path, pages: int = 250, seed: int = 0, empty_every: int = 0) -> Path:
    return write_pages(path, book_lines(pages, seed, empty_every))


def scanned_book(path: Path, pages: int = 10) -> Path:
    """Pages with only a drawn image-like rectangle, no text layer."""
    doc = fitz.open()
    for _ in range(pages):
        page = doc.new_page()
        page.draw_rect(fitz.Rect(50, 50, 550, 750), color=(0, 0, 0), fill=(0.9, 0.9, 0.9))
    doc.save(path)
    doc.close()
    return Path(path)


def encrypted_book(path: Path) -> Path:
    doc = fitz.open()
    doc.new_page().insert_text((50, 50), "secret text")
    doc.save(path, encryption=fitz.PDF_ENCRYPT_AES_256, user_pw="pw", owner_pw="pw")
    doc.close()
    return Path(path)


def corrupt_file(path: Path) -> Path:
    Path(path).write_bytes(b"%PDF-1.7\n" + random.Random(0).randbytes(4096))
    return Path(path)


def main() -> None:
    p = argparse.ArgumentParser(prog="python -m stress.make_pdf")
    p.add_argument("kind", choices=["book", "scanned", "encrypted", "corrupt"])
    p.add_argument("out", type=Path)
    p.add_argument("--pages", type=int, default=250)
    p.add_argument("--seed", type=int, default=0)
    args = p.parse_args()
    if args.kind == "book":
        text_book(args.out, args.pages, args.seed)
    elif args.kind == "scanned":
        scanned_book(args.out, args.pages)
    elif args.kind == "encrypted":
        encrypted_book(args.out)
    else:
        corrupt_file(args.out)
    print(args.out)


if __name__ == "__main__":
    main()
