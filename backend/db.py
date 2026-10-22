"""Database connections and schema setup."""
from contextlib import contextmanager

import psycopg
from pgvector.psycopg import register_vector
from psycopg import sql

import config


@contextmanager
def connect(url: str | None = None):
    """Yield a connection with the pgvector type registered. Commits on success."""
    with psycopg.connect(url or config.DATABASE_URL) as conn:
        register_vector(conn)
        yield conn


def apply_schema(url: str | None = None) -> None:
    schema = (config.ROOT / "schema.sql").read_text()
    with psycopg.connect(url or config.DATABASE_URL) as conn:
        conn.execute(schema)


def ensure_database(url: str) -> None:
    """Create the database named in `url` if missing (used by tests and stress runs)."""
    info = psycopg.conninfo.conninfo_to_dict(url)
    name = info["dbname"]
    admin = psycopg.conninfo.make_conninfo(url, dbname="postgres")
    with psycopg.connect(admin, autocommit=True) as conn:
        exists = conn.execute("SELECT 1 FROM pg_database WHERE datname = %s", (name,)).fetchone()
        if not exists:
            conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    apply_schema(url)
