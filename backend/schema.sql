CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS books (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  title        TEXT NOT NULL,
  author       TEXT,
  file_path    TEXT NOT NULL,
  file_sha256  TEXT UNIQUE NOT NULL,
  page_count   INT,
  status       TEXT NOT NULL DEFAULT 'indexing',  -- indexing | ready | failed
  error        TEXT,
  embed_model  TEXT,
  embed_dim    INT,
  created_at   TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS chunks (
  id           BIGSERIAL PRIMARY KEY,
  book_id      UUID NOT NULL REFERENCES books(id) ON DELETE CASCADE,
  ordinal      INT  NOT NULL,
  page_start   INT  NOT NULL,
  page_end     INT  NOT NULL,
  content      TEXT NOT NULL,
  token_count  INT  NOT NULL,
  embedding    vector(1024) NOT NULL,
  UNIQUE (book_id, ordinal)
);

CREATE INDEX IF NOT EXISTS chunks_book_idx ON chunks (book_id);

-- Fields the reader UI needs (added after the first release; safe to re-run).
ALTER TABLE books ADD COLUMN IF NOT EXISTS file_name      TEXT;
ALTER TABLE books ADD COLUMN IF NOT EXISTS file_size      BIGINT;
ALTER TABLE books ADD COLUMN IF NOT EXISTS last_page      INT NOT NULL DEFAULT 1;
ALTER TABLE books ADD COLUMN IF NOT EXISTS last_opened_at TIMESTAMPTZ;
