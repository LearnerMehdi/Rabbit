from dataclasses import dataclass
from typing import Callable

ProgressFn = Callable[[str, float], None]


@dataclass
class PageText:
    page: int  # 1-based
    text: str


class PageList(list):
    """list[PageText] plus flags set by the pipeline steps."""

    needs_ocr: bool = False

    @property
    def page_count(self) -> int:
        return len(self)

    @property
    def empty_pages(self) -> int:
        return sum(1 for p in self if not p.text.strip())


@dataclass
class Chunk:
    ordinal: int
    page_start: int
    page_end: int
    content: str
    token_count: int


@dataclass
class IngestResult:
    book_id: str
    page_count: int
    chunk_count: int
    empty_page_count: int
    duration_s: float


class IngestError(Exception):
    """Expected failure with a message short enough to show in the UI."""


class UnreadablePDFError(IngestError):
    pass


class NotPdfError(IngestError):
    def __init__(self):
        super().__init__("Not a PDF file")


class NoTextLayerError(IngestError):
    def __init__(self):
        super().__init__("No text layer (scanned PDF)")


class DuplicateBookError(IngestError):
    def __init__(self, existing_id):
        self.existing_id = existing_id
        super().__init__(f"This file is already in the library (book {existing_id})")


class BookNotFoundError(IngestError):
    pass
