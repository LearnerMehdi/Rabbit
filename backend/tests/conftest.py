import os

import pytest

from embedder import get_tokenizer

TEST_DB_URL = os.environ.get(
    "RABBIT_TEST_DATABASE_URL", "postgresql://rabbit:rabbit@localhost:5432/orange_rabbit_test"
)


@pytest.fixture(scope="session")
def tok():
    return get_tokenizer()


@pytest.fixture(scope="session")
def db_url():
    import psycopg

    import db

    try:
        db.ensure_database(TEST_DB_URL)
    except psycopg.OperationalError as e:
        pytest.skip(f"test database unavailable: {e}")
    return TEST_DB_URL


class RealLLMCall(BaseException):
    """BaseException so answer_question's error handling can't turn it into a normal failure."""


@pytest.fixture(autouse=True)
def no_real_llm_calls(monkeypatch):
    """Tests never reach the real LLM (its API has a tight request budget).
    A test that needs an answer replaces chat.answer._post_completion with a stub."""
    import chat.answer

    def refuse(messages, settings):
        raise RealLLMCall("a test tried to call the real LLM")

    monkeypatch.setattr(chat.answer, "_post_completion", refuse)
