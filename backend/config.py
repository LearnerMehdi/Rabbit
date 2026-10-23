"""Runtime configuration: ../config.yaml, overridden per value by RABBIT_* environment
variables. Secrets (the LLM API key) come from the environment, loaded from ../../.env."""
import os
from dataclasses import dataclass
from pathlib import Path

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent  # backend/
PROJECT_ROOT = ROOT.parent  # Rabbit/Rabbit/, where config.yaml lives

load_dotenv(PROJECT_ROOT.parent / ".env")  # never overrides variables already set


@dataclass(frozen=True)
class Settings:
    host: str
    port: int
    database_url: str
    data_dir: Path
    embed_backend: str
    embed_model: str
    embed_dim: int
    embed_device: str
    embed_batch_size: int
    chunk_size: int
    chunk_overlap: int
    empty_page_ratio: float
    chat_top_k: int
    llm_base_url: str
    llm_model: str
    llm_api_key: str | None
    llm_temperature: float
    llm_max_tokens: int
    llm_timeout_s: float


def load(path: Path | None = None, env: dict | None = None) -> Settings:
    env = os.environ if env is None else env
    path = Path(path or env.get("RABBIT_CONFIG") or PROJECT_ROOT / "config.yaml")
    cfg = (yaml.safe_load(path.read_text()) or {}) if path.is_file() else {}

    def get(key: str, var: str, default, cast=str):
        if var in env:
            return cast(env[var])
        node = cfg
        for part in key.split("."):
            if not isinstance(node, dict) or part not in node:
                return cast(default)
            node = node[part]
        return cast(node)

    data_dir = Path(get("storage.data_dir", "RABBIT_DATA_DIR", "backend/data"))
    key_var = get("chat.llm.api_key_env", "RABBIT_LLM_API_KEY_ENV", "OPENROUTER_API_KEY")
    return Settings(
        host=get("server.host", "RABBIT_HOST", "127.0.0.1"),
        port=get("server.port", "RABBIT_PORT", 8000, int),
        database_url=get(
            "database.url", "RABBIT_DATABASE_URL", "postgresql://rabbit:rabbit@localhost:5432/orange_rabbit"
        ),
        data_dir=data_dir if data_dir.is_absolute() else PROJECT_ROOT / data_dir,
        embed_backend=get("embedder.backend", "RABBIT_EMBED_BACKEND", "local"),
        embed_model=get("embedder.model", "RABBIT_EMBED_MODEL", "Qwen/Qwen3-Embedding-0.6B"),
        embed_dim=get("embedder.dim", "RABBIT_EMBED_DIM", 1024, int),
        embed_device=get("embedder.device", "RABBIT_EMBED_DEVICE", "auto"),  # auto | cuda | cpu
        embed_batch_size=get("embedder.batch_size", "RABBIT_EMBED_BATCH_SIZE", 16, int),
        chunk_size=get("ingest.chunk_size", "RABBIT_CHUNK_SIZE", 500, int),
        chunk_overlap=get("ingest.chunk_overlap", "RABBIT_CHUNK_OVERLAP", 75, int),
        # clean_text: a book is "scanned" when more than this fraction of pages is empty.
        empty_page_ratio=get("ingest.empty_page_ratio", "RABBIT_EMPTY_PAGE_RATIO", 0.8, float),
        chat_top_k=get("chat.top_k", "RABBIT_CHAT_TOP_K", 8, int),
        llm_base_url=get("chat.llm.base_url", "RABBIT_LLM_BASE_URL", "https://openrouter.ai/api/v1"),
        llm_model=get("chat.llm.model", "RABBIT_LLM_MODEL", "openai/gpt-4o"),
        llm_api_key=env.get(key_var) or None,
        llm_temperature=get("chat.llm.temperature", "RABBIT_LLM_TEMPERATURE", 0.2, float),
        llm_max_tokens=get("chat.llm.max_tokens", "RABBIT_LLM_MAX_TOKENS", 1024, int),
        llm_timeout_s=get("chat.llm.timeout_s", "RABBIT_LLM_TIMEOUT_S", 60, float),
    )


SETTINGS = load()

HOST = SETTINGS.host
PORT = SETTINGS.port
DATABASE_URL = SETTINGS.database_url
DATA_DIR = SETTINGS.data_dir
BOOKS_DIR = DATA_DIR / "books"

# The embedder package reads only RABBIT_EMBED_* (it stays independent of this module),
# so hand it the configured values unless the environment already sets them.
EMBED_BACKEND = SETTINGS.embed_backend
EMBED_MODEL = SETTINGS.embed_model
EMBED_DIM = SETTINGS.embed_dim
EMBED_DEVICE = SETTINGS.embed_device
EMBED_BATCH_SIZE = SETTINGS.embed_batch_size
for _var, _value in {
    "RABBIT_EMBED_BACKEND": EMBED_BACKEND,
    "RABBIT_EMBED_MODEL": EMBED_MODEL,
    "RABBIT_EMBED_DIM": str(EMBED_DIM),
    "RABBIT_EMBED_DEVICE": EMBED_DEVICE,
}.items():
    os.environ.setdefault(_var, _value)

CHUNK_SIZE = SETTINGS.chunk_size
CHUNK_OVERLAP = SETTINGS.chunk_overlap
EMPTY_PAGE_RATIO = SETTINGS.empty_page_ratio

CHAT_TOP_K = SETTINGS.chat_top_k
