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
