from pathlib import Path

import pymupdf as fitz

from .types import PageList, PageText, UnreadablePDFError


def extract_pages(pdf_path: Path) -> PageList:
    """Plain text of every page, 1-based page numbers. `.page_count` on the result."""
    try:
        doc = fitz.open(pdf_path)
    except Exception as e:
        raise UnreadablePDFError("Cannot open PDF (damaged or not a PDF)") from e
    with doc:
        if not doc.is_pdf:
            raise UnreadablePDFError("Not a PDF file")
        if doc.needs_pass:
            raise UnreadablePDFError("PDF is password-protected")
        if doc.page_count == 0:
            raise UnreadablePDFError("PDF has no pages")
        pages = PageList()
        for i, page in enumerate(doc, start=1):
            try:
                pages.append(PageText(page=i, text=page.get_text("text")))
            except Exception as e:
                raise UnreadablePDFError(f"Cannot read page {i}: {e}") from e
    return pages
