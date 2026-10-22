"""Pack paragraphs into ~`size`-token chunks with `overlap` tokens carried over."""
import re
from dataclasses import dataclass

import config
from embedder import Tokenizer, get_tokenizer

from .types import Chunk, PageText

_SENTENCE_END = re.compile(r"(?<=[.!?…])[\"'”’)\]]*\s+")
SEP = "\n\n"


@dataclass
class _Piece:
    text: str
    page: int
    sep: str = SEP  # joins it to the previous piece: SEP between paragraphs, " " within one


def _split_sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENTENCE_END.split(text) if s.strip()]


def _hard_split(text: str, limit: int, tok: Tokenizer) -> list[str]:
    offs = tok.offsets(text)
    parts = []
    for i in range(0, len(offs), limit):
        end = offs[i + limit][0] if i + limit < len(offs) else len(text)
        parts.append(text[offs[i][0] : end].strip())
    return [p for p in parts if p]


def _pieces(pages: list[PageText], limit: int, tok: Tokenizer) -> list[tuple[_Piece, int]]:
    """(piece, token count) in reading order: whole paragraphs, or the sentences of
    paragraphs longer than `limit` tokens (sentences still too long are cut by tokens)."""
    out = []
    for page in pages:
        for para in page.text.split(SEP):
            para = para.strip()
            if not para:
                continue
            n = tok.count(para)
            if n <= limit:
                out.append((_Piece(para, page.page), n))
                continue
            sep = SEP
            for sent in _split_sentences(para):
                parts = [sent] if tok.count(sent) <= limit else _hard_split(sent, limit, tok)
                for part in parts:
                    out.append((_Piece(part, page.page, sep), tok.count(part)))
                    sep = " "
    return out


class _Builder:
    """Chunk content plus the page of every character span in it."""

    def __init__(self):
        self.text = ""
        self.spans: list[tuple[int, int, int]] = []  # (start, end, page)

    def add(self, piece: _Piece):
        text, page = piece.text, piece.page
        if self.text:
            self.text += piece.sep
        start = len(self.text)
        self.text += text
        self.spans.append((start, len(self.text), page))

    def candidate(self, piece: _Piece) -> str:
        return f"{self.text}{piece.sep}{piece.text}" if self.text else piece.text

    def tail(self, n_tokens: int, tok: Tokenizer) -> "_Builder":
        """Last `n_tokens` tokens as a new builder (keeps page attribution)."""
        new = _Builder()
        if n_tokens <= 0 or not self.text:
            return new
        offs = tok.offsets(self.text)
        if len(offs) <= n_tokens:
            cut = 0
        else:
            cut = offs[-n_tokens][0]
            # don't start mid-word: move to the next whitespace boundary if one is close
            ws = self.text.find(" ", cut)
            if 0 <= ws < offs[-1][0] and self.text[cut - 1 : cut].strip():
                cut = ws + 1
        for start, end, page in self.spans:
            if end <= cut:
                continue
            s = max(start, cut)
            new.spans.append((len(new.text) + s - cut, len(new.text) + end - cut, page))
        new.text = self.text[cut:]
        return new

    @property
    def pages(self) -> tuple[int, int]:
        return min(p for *_, p in self.spans), max(p for *_, p in self.spans)


def chunk_pages(
    pages: list[PageText],
    size: int | None = None,
    overlap: int | None = None,
    tokenizer: Tokenizer | None = None,
) -> list[Chunk]:
    size = config.CHUNK_SIZE if size is None else size
    overlap = config.CHUNK_OVERLAP if overlap is None else overlap
    if not 0 <= overlap < size:
        raise ValueError("need 0 <= overlap < size")
    tok = tokenizer or get_tokenizer()
    # every piece must fit in a chunk together with the carried-over overlap
    # (+2 tokens of slack for the paragraph separator)
    pieces = _pieces(pages, size - overlap - 2, tok)

    chunks: list[Chunk] = []
    cur = _Builder()
    cur_tokens = 0  # running estimate (sum of parts + separators); exact near the limit
    has_new = False  # does `cur` contain anything beyond the overlap prefix?
    margin = 8

    def flush():
        nonlocal cur, cur_tokens, has_new
        start, end = cur.pages
        chunks.append(Chunk(len(chunks), start, end, cur.text, tok.count(cur.text)))
        cur = cur.tail(overlap, tok)
        cur_tokens = tok.count(cur.text)
        has_new = False

    for piece, n in pieces:
        add = n + 2
        if has_new and cur_tokens + add > size - margin and tok.count(cur.candidate(piece)) > size:
            flush()
        cur.add(piece)
        has_new = True
        cur_tokens += add
        if cur_tokens > size - margin:
            cur_tokens = tok.count(cur.text)
        # overlap + piece can still overflow by a token or two of tokenizer merges
        while cur_tokens > size:
            cur = cur.tail(size - 1, tok)
            cur_tokens = tok.count(cur.text)
    if has_new:
        flush()
    return chunks
