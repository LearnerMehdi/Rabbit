"""Questions: top-k retrieval with the real embedder; the LLM call is always a stub."""
import dataclasses
import uuid

import pytest
from fastapi.testclient import TestClient

import chat.answer
import config
from api.app import create_app
from chat import (
    SYSTEM_PROMPT,
    BookNotReadyError,
    ChatUnavailableError,
    answer_question,
    PageWords,
    build_messages,
    locate,
    search_chunks,
)
from embedder import get_embedder
from ingest import add_book, create_book, delete_book
from stress import make_pdf

pytestmark = pytest.mark.integration

FACT_PAGE = 7
FACT = (
    "The lighthouse keeper on Kessler Island recorded the height of the tide every morning "
    "with a brass gauge that his grandfather had built from a ship's anchor chain."
)
QUESTION = "What did the lighthouse keeper use to record the tide?"

WITH_KEY = dataclasses.replace(config.SETTINGS, llm_api_key="test-key", chat_top_k=4)


@pytest.fixture(scope="module")
def book(db_url, tmp_path_factory):
    """A 12-page book of filler text with one real fact on page 7, indexed."""
    tmp = tmp_path_factory.mktemp("chat")
    pages = make_pdf.book_lines(12, seed=uuid.uuid4().int % 10**6)
    pages[FACT_PAGE - 1] = (make_pdf._wrap(FACT, make_pdf.random.Random(0)) + [""] + pages[FACT_PAGE - 1])[
        : make_pdf.LINES_PER_PAGE
    ]
    pdf = make_pdf.write_pages(tmp / "fact.pdf", pages)
    books_dir = tmp / "books"
    book_id = add_book(pdf, "Island notes", db_url=db_url, books_dir=books_dir)
    yield book_id
    delete_book(book_id, db_url=db_url, books_dir=books_dir)


class SpyEmbedder:
    def __init__(self, inner):
        self.inner, self.model_name, self.dim = inner, inner.model_name, inner.dim
        self.query_calls = []

    def embed_queries(self, texts):
        self.query_calls.append(list(texts))
        return self.inner.embed_queries(texts)

    def embed_documents(self, texts):
        raise AssertionError("questions must not be embedded as documents")


@pytest.fixture
def stub_llm(monkeypatch):
    """Replaces the one network call; records every request it would have sent."""
    calls = []

    def fake(messages, settings):
        calls.append(messages)
        return f"stub answer {len(calls)}"

    monkeypatch.setattr(chat.answer, "_post_completion", fake)
    return calls


def test_search_returns_k_closest_chunks_in_order(book, db_url):
    spy = SpyEmbedder(get_embedder())
    hits = search_chunks(book, QUESTION, 4, embedder=spy, db_url=db_url)
    assert spy.query_calls == [[QUESTION]]  # the question as typed, embedded once
    assert len(hits) == 4
    assert [h.distance for h in hits] == sorted(h.distance for h in hits)
    assert hits[0].page_start <= FACT_PAGE <= hits[0].page_end
    assert "brass gauge" in hits[0].content


def test_messages_are_system_prompt_plus_this_question_and_chunks(book, db_url, stub_llm):
    first = answer_question(book, QUESTION, db_url=db_url, settings=WITH_KEY)
    second = answer_question(book, "Who built the gauge?", db_url=db_url, settings=WITH_KEY)
    assert (first.text, second.text) == ("stub answer 1", "stub answer 2")

    # every call is isolated: [system, user], same system prompt, nothing from earlier calls
    for messages in stub_llm:
        assert [m["role"] for m in messages] == ["system", "user"]
        assert messages[0]["content"] == SYSTEM_PROMPT
    user1, user2 = stub_llm[0][1]["content"], stub_llm[1][1]["content"]
    assert user1.endswith(f"Question: {QUESTION}")
    assert user2.endswith("Question: Who built the gauge?")
    assert QUESTION not in user2 and "stub answer 1" not in user2
    assert user1.count("[p. ") == WITH_KEY.chat_top_k
    assert "brass gauge" in user1


def test_build_messages_without_chunks():
    [system, user] = build_messages("Anything?", [])
    assert system == {"role": "system", "content": SYSTEM_PROMPT}
    assert user == {"role": "user", "content": "Question: Anything?"}


def test_not_ready_and_unavailable(db_url, tmp_path, stub_llm):
    pdf = make_pdf.text_book(tmp_path / "x.pdf", pages=2, seed=uuid.uuid4().int % 10**6)
    pending = create_book(pdf, "Not indexed yet", db_url=db_url, books_dir=tmp_path / "books")
    try:
        with pytest.raises(BookNotReadyError):
            answer_question(pending, QUESTION, db_url=db_url, settings=WITH_KEY)
        with pytest.raises(ChatUnavailableError):
            answer_question(pending, QUESTION, db_url=db_url, settings=dataclasses.replace(WITH_KEY, llm_api_key=None))
    finally:
        delete_book(pending, db_url=db_url, books_dir=tmp_path / "books")
    assert stub_llm == []


def test_ask_endpoint(book, db_url, tmp_path, stub_llm):
    app = create_app(db_url=db_url, books_dir=tmp_path, dist_dir=None, warm_up=False, settings=WITH_KEY)
    with TestClient(app) as client:
        assert client.get("/api/chat/availability").json() == {"availability": "available"}
        r = client.post(f"/api/books/{book}/ask", json={"question": f"  {QUESTION}  "})
        body = r.json()
        assert body["answer"] == "stub answer 1"
        assert [s["n"] for s in body["sources"]] == list(range(1, WITH_KEY.chat_top_k + 1))
        top = body["sources"][0]
        assert "brass gauge" in top["text"] and 0 < top["similarity"] <= 1
        assert FACT_PAGE in [h["page"] for h in top["highlights"]]
        assert stub_llm[0][1]["content"].endswith(f"Question: {QUESTION}")

    no_key = create_app(
        db_url=db_url, books_dir=tmp_path, dist_dir=None, warm_up=False,
        settings=dataclasses.replace(WITH_KEY, llm_api_key=None),
    )
    with TestClient(no_key) as client:
        assert client.get("/api/chat/availability").json() == {"availability": "unavailable"}
        r = client.post(f"/api/books/{book}/ask", json={"question": QUESTION})
        assert (r.status_code, r.json()["code"]) == (503, "unavailable")
    assert len(stub_llm) == 1


def test_llm_failure_is_reported_not_raised(book, db_url, tmp_path, monkeypatch):
    def broken(messages, settings):
        raise TimeoutError("provider timed out")

    monkeypatch.setattr(chat.answer, "_post_completion", broken)
    app = create_app(db_url=db_url, books_dir=tmp_path, dist_dir=None, warm_up=False, settings=WITH_KEY)
    with TestClient(app) as client:
        r = client.post(f"/api/books/{book}/ask", json={"question": QUESTION})
        assert (r.status_code, r.json()) == (502, {"code": "failed", "message": "Couldn't get an answer. Try again."})


def test_sources_highlight_the_excerpt_on_its_page(book, db_url, stub_llm):
    """Sources are for the UI: located in the PDF, never shown to the LLM."""
    answer = answer_question(book, QUESTION, db_url=db_url, settings=WITH_KEY)
    assert len(answer.sources) == WITH_KEY.chat_top_k
    for s in answer.sources:
        assert s.highlights, f"excerpt {s.n} not found on p. {s.excerpt.page_start}-{s.excerpt.page_end}"
        for h in s.highlights:
            assert s.excerpt.page_start <= h.page <= s.excerpt.page_end
            for x0, y0, x1, y1 in h.rects:
                assert 0 <= x0 < x1 <= 1 and 0 <= y0 < y1 <= 1
    # the fact opens its page, so the top excerpt is highlighted from near the top margin there
    [top] = [h for h in answer.sources[0].highlights if h.page == FACT_PAGE]
    assert min(r[1] for r in top.rects) < 0.2
    user = stub_llm[0][1]["content"]
    assert "highlight" not in user.lower() and "[1]" not in user


def test_locate_falls_back_to_word_runs(tmp_path):
    """Text that isn't verbatim in the PDF still lights up its matching runs of words."""
    pdf = make_pdf.write_pages(tmp_path / "f.pdf", [make_pdf._wrap(FACT, make_pdf.random.Random(0))])
    with PageWords(pdf) as pages:
        altered = FACT.replace("brass gauge", "bronze meter")
        [h] = locate(pages, 1, 1, altered)
        assert h.page == 1 and h.rects
        assert locate(pages, 1, 1, "completely unrelated words that are nowhere here") == []
