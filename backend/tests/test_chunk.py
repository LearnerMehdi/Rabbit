import random
import re

import pytest

from ingest import PageText, chunk_pages
from ingest.chunk import SEP

WORDS = "alpha beta gamma delta energy matrix vector system boundary model data field".split()


def sentence(rng, page, n=None):
    words = [rng.choice(WORDS) for _ in range(n or rng.randint(5, 20))]
    return f"P{page}m " + " ".join(words) + "."


def make_pages(n_pages, paras=(2, 5), sents=(2, 8), seed=0, empty=()):
    rng = random.Random(seed)
    pages = []
    for p in range(1, n_pages + 1):
        if p in empty:
            pages.append(PageText(p, ""))
            continue
        text = SEP.join(
            " ".join(sentence(rng, p) for _ in range(rng.randint(*sents)))
            for _ in range(rng.randint(*paras))
        )
        pages.append(PageText(p, text))
    return pages


def shared_prefix(prev: str, nxt: str) -> str:
    """Longest prefix of `nxt` that is a suffix of `prev`."""
    for n in range(min(len(prev), len(nxt)), 0, -1):
        if prev.endswith(nxt[:n]):
            return nxt[:n]
    return ""


def markers(text):
    return [int(m) for m in re.findall(r"P(\d+)m", text)]


@pytest.mark.parametrize("size,overlap", [(500, 75), (120, 20), (64, 0)])
def test_chunks_within_size(tok, size, overlap):
    chunks = chunk_pages(make_pages(30), size=size, overlap=overlap, tokenizer=tok)
    assert len(chunks) > 3
    for c in chunks:
        assert c.token_count == tok.count(c.content)
        assert 0 < c.token_count <= size


def test_chunks_are_reasonably_full(tok):
    chunks = chunk_pages(make_pages(40), size=500, overlap=75, tokenizer=tok)
    # whole paragraphs are packed, so a chunk closes early when the next one won't fit
    sizes = [c.token_count for c in chunks[:-1]]
    assert min(sizes) > 0.6 * 500
    assert sum(sizes) / len(sizes) > 0.8 * 500


def test_ordinals_continuous(tok):
    chunks = chunk_pages(make_pages(20), size=200, overlap=30, tokenizer=tok)
    assert [c.ordinal for c in chunks] == list(range(len(chunks)))


def test_overlap_present(tok):
    overlap = 75
    chunks = chunk_pages(make_pages(30), size=500, overlap=overlap, tokenizer=tok)
    for prev, nxt in zip(chunks, chunks[1:]):
        shared = shared_prefix(prev.content, nxt.content)
        assert shared, f"no overlap between {prev.ordinal} and {nxt.ordinal}"
        assert overlap - 10 <= tok.count(shared) <= overlap


def test_no_overlap_when_zero(tok):
    chunks = chunk_pages(make_pages(20), size=200, overlap=0, tokenizer=tok)
    for prev, nxt in zip(chunks, chunks[1:]):
        assert not nxt.content.startswith(prev.content[-20:])
    # no text lost or repeated
    joined = " ".join(c.content.replace(SEP, " ") for c in chunks)
    original = " ".join(p.text.replace(SEP, " ") for p in make_pages(20))
    assert joined == original


def test_page_ranges(tok):
    pages = make_pages(25, empty={7, 8, 15})
    chunks = chunk_pages(pages, size=150, overlap=25, tokenizer=tok)
    assert chunks[0].page_start == 1
    assert chunks[-1].page_end == 25
    for c in chunks:
        found = markers(c.content)
        assert c.page_start <= min(found) and max(found) <= c.page_end
        assert c.page_end == max(found)
        # the overlap prefix may begin mid-sentence, cutting off its page marker
        assert min(found) - c.page_start <= 3
        assert not {7, 8, 15} & {c.page_start, c.page_end}
    # page ranges never go backwards
    assert all(a.page_start <= b.page_start and a.page_end <= b.page_end for a, b in zip(chunks, chunks[1:]))


def test_long_paragraph_split_at_sentences(tok):
    rng = random.Random(1)
    para = " ".join(sentence(rng, 1) for _ in range(200))  # one paragraph, thousands of tokens
    chunks = chunk_pages([PageText(1, para)], size=200, overlap=30, tokenizer=tok)
    assert len(chunks) > 5
    for c in chunks:
        assert c.token_count <= 200
        assert c.content.endswith(".")  # every chunk ends on a sentence boundary


def test_giant_sentence_hard_split(tok):
    rng = random.Random(2)
    giant = sentence(rng, 1, n=1500)
    chunks = chunk_pages([PageText(1, giant)], size=128, overlap=16, tokenizer=tok)
    assert len(chunks) > 5
    assert all(c.token_count <= 128 for c in chunks)


def test_empty_input(tok):
    assert chunk_pages([PageText(1, ""), PageText(2, "")], tokenizer=tok) == []


def test_bad_overlap(tok):
    with pytest.raises(ValueError):
        chunk_pages(make_pages(2), size=100, overlap=100, tokenizer=tok)
