import re

import config

from .types import PageList, PageText

_HYPHEN_BREAK = re.compile(r"(\w)-[ \t]*\n[ \t]*([a-z])")
_HYPHEN_KEEP = re.compile(r"(\w-)\n(?=\w)")
_PARA_BREAK = re.compile(r"\n[ \t]*\n\s*")
_SPACES = re.compile(r"[ \t\f\v  - 　]+")


def clean_page(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("­", "")
    text = _SPACES.sub(" ", text)
    text = "\n".join(line.strip() for line in text.split("\n"))
    text = _HYPHEN_BREAK.sub(r"\1\2", text)  # diffu-\nsion -> diffusion
    text = _HYPHEN_KEEP.sub(r"\1", text)  # Jean-\nPaul -> Jean-Paul
    paragraphs = _PARA_BREAK.split(text.strip())
    paragraphs = [" ".join(p.split("\n")).strip() for p in paragraphs]
    paragraphs = [_SPACES.sub(" ", p) for p in paragraphs if p]
    return "\n\n".join(paragraphs)


def clean_text(pages: list[PageText], empty_ratio: float | None = None) -> PageList:
    """Minimal cleanup. Sets `needs_ocr` when more than `empty_ratio` of pages are empty."""
    empty_ratio = config.EMPTY_PAGE_RATIO if empty_ratio is None else empty_ratio
    out = PageList(PageText(page=p.page, text=clean_page(p.text)) for p in pages)
    out.needs_ocr = not out or out.empty_pages / len(out) > empty_ratio
    return out
