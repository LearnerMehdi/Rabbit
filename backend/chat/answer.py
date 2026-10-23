"""Answer one question about one book with one LLM call.

Every call is isolated: the same system prompt, plus a user message built from this
question and the chunks retrieved for it. Nothing is stored and no history is sent.
"""
import logging
from uuid import UUID

import httpx

import config
from embedder import Embedder
from ingest import get_book

from .retrieve import Excerpt, search_chunks

log = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You answer questions about a book. Use only the excerpts from the book that come with "
    "the question. If they don't contain the answer, say that this part of the book doesn't "
    "cover it. Answer plainly and concisely, in the language of the question."
)


class ChatUnavailableError(Exception):
    """No LLM API key is configured."""


class BookNotReadyError(Exception):
    """The book is still being prepared, or preparing it failed."""


class AnswerFailedError(Exception):
    """The LLM call failed or returned nothing usable."""


def chat_available(settings: config.Settings = config.SETTINGS) -> bool:
    return bool(settings.llm_api_key)


def build_messages(question: str, excerpts: list[Excerpt]) -> list[dict]:
    """[system, user]: the shared system prompt, then this call's excerpts and question."""
    parts = []
    if excerpts:
        parts.append("Excerpts from the book:")
        for e in excerpts:
            pages = f"p. {e.page_start}" if e.page_start == e.page_end else f"p. {e.page_start}–{e.page_end}"
            parts.append(f"[{pages}]\n{e.content}")
    parts.append(f"Question: {question}")
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": "\n\n".join(parts)},
    ]


def _post_completion(messages: list[dict], settings: config.Settings) -> str:
    """The only network call: one OpenAI-compatible chat completion."""
    resp = httpx.post(
        f"{settings.llm_base_url.rstrip('/')}/chat/completions",
        headers={"Authorization": f"Bearer {settings.llm_api_key}", "Accept": "application/json"},
        json={
            "model": settings.llm_model,
            "messages": messages,
            "temperature": settings.llm_temperature,
            "max_tokens": settings.llm_max_tokens,
            "stream": False,
        },
        timeout=settings.llm_timeout_s,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


def answer_question(
    book_id: UUID,
    question: str,
    *,
    embedder: Embedder | None = None,
    db_url: str | None = None,
    settings: config.Settings = config.SETTINGS,
) -> str:
    if not chat_available(settings):
        raise ChatUnavailableError()
    if get_book(book_id, db_url=db_url)["status"] != "ready":
        raise BookNotReadyError()
    excerpts = search_chunks(book_id, question, settings.chat_top_k, embedder=embedder, db_url=db_url)
    try:
        answer = (_post_completion(build_messages(question, excerpts), settings) or "").strip()
    except Exception as e:
        log.warning("LLM call failed for book %s: %s", book_id, e)
        raise AnswerFailedError() from e
    if not answer:
        raise AnswerFailedError()
    return answer
