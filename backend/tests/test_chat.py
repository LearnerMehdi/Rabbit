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
    build_messages,
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
    assert (first, second) == ("stub answer 1", "stub answer 2")

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
        assert r.json() == {"answer": "stub answer 1"}
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

