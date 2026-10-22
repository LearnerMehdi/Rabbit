"""Runtime configuration, read from environment variables (RABBIT_*)."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent

DATABASE_URL = os.environ.get(
    "RABBIT_DATABASE_URL", "postgresql://rabbit:rabbit@localhost:5432/orange_rabbit"
)
DATA_DIR = Path(os.environ.get("RABBIT_DATA_DIR", ROOT / "data"))
BOOKS_DIR = DATA_DIR / "books"

# Embedder backend: "local" (in-process sentence-transformers). An "http" backend
# will be added once the embedder runs as its own service.
EMBED_BACKEND = os.environ.get("RABBIT_EMBED_BACKEND", "local")
EMBED_MODEL = os.environ.get("RABBIT_EMBED_MODEL", "Qwen/Qwen3-Embedding-0.6B")
EMBED_DIM = int(os.environ.get("RABBIT_EMBED_DIM", "1024"))
EMBED_DEVICE = os.environ.get("RABBIT_EMBED_DEVICE", "auto")  # auto | cuda | cpu
EMBED_BATCH_SIZE = int(os.environ.get("RABBIT_EMBED_BATCH_SIZE", "16"))

CHUNK_SIZE = int(os.environ.get("RABBIT_CHUNK_SIZE", "500"))
CHUNK_OVERLAP = int(os.environ.get("RABBIT_CHUNK_OVERLAP", "75"))

# clean_text: a book is "scanned" when more than this fraction of pages is empty.
EMPTY_PAGE_RATIO = float(os.environ.get("RABBIT_EMPTY_PAGE_RATIO", "0.8"))
