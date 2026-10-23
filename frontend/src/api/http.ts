/**
 * LibraryApi over HTTP: the backend in backend/api/app.py, served from the same origin.
 * Progress and library changes arrive as server-sent events on /api/events.
 */
import {
  ApiError,
  type ApiErrorCode,
  type Book,
  type BookProgress,
  type ChatAvailability,
  type LibraryApi,
  type OpenedBook,
  type SortKey,
} from "./types";

const CODES: ApiErrorCode[] = ["not_pdf", "duplicate", "not_found", "not_ready", "unavailable", "failed"];

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`/api${path}`, init);
  } catch {
    throw new ApiError("failed", "Can't reach Orange Reader. Check that it is running.");
  }
  if (!res.ok) {
    const body = (await res.json().catch(() => null)) as { code?: string; message?: string } | null;
    const code = CODES.includes(body?.code as ApiErrorCode) ? (body!.code as ApiErrorCode) : "failed";
    throw new ApiError(code, body?.message ?? "Something went wrong. Try again.");
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

const json = (method: string, body: unknown): RequestInit => ({
  method,
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

export class HttpApi implements LibraryApi {
  private events: EventSource | null = null;
  private progressListeners = new Map<string, Set<(p: BookProgress) => void>>();
  private libraryListeners = new Set<() => void>();

  /** one EventSource for the whole app, opened on the first subscription */
  private connect() {
    if (this.events) return;
    const es = new EventSource("/api/events");
    es.addEventListener("progress", (e) => {
      const { bookId, ...p } = JSON.parse((e as MessageEvent).data) as BookProgress & { bookId: string };
      this.progressListeners.get(bookId)?.forEach((cb) => cb(p));
    });
    es.addEventListener("library", () => this.libraryListeners.forEach((cb) => cb()));
    es.addEventListener("deleted", (e) => {
      const { bookId } = JSON.parse((e as MessageEvent).data) as { bookId: string };
      this.progressListeners.delete(bookId);
    });
    // after a reconnect (e.g. the server restarted) refresh everything that may be stale
    let opened = false;
    es.addEventListener("open", () => {
      if (opened) this.libraryListeners.forEach((cb) => cb());
      opened = true;
    });
    this.events = es;
  }

  listBooks({ query = "", sort = "added" }: { query?: string; sort?: SortKey } = {}): Promise<Book[]> {
    return request(`/books?${new URLSearchParams({ query, sort })}`);
  }

  addBook(file: File, meta: { title: string; author?: string | null }): Promise<Book> {
    const form = new FormData();
    form.append("file", file, file.name);
    form.append("title", meta.title.trim());
    if (meta.author?.trim()) form.append("author", meta.author.trim());
    return request("/books", { method: "POST", body: form });
  }

  reindexBook(bookId: string): Promise<void> {
    return request(`/books/${bookId}/reindex`, { method: "POST" });
  }

  async openBook(bookId: string): Promise<OpenedBook> {
    const book = await request<Book>(`/books/${bookId}/open`, { method: "POST" });
    let res: Response;
    try {
      res = await fetch(`/api/books/${bookId}/file`);
    } catch {
      throw new ApiError("failed", "Can't reach Orange Reader. Check that it is running.");
    }
    if (!res.ok) throw new ApiError("not_found", "The PDF for this book is missing.");
    return { book, file: await res.blob() };
  }

  updateBook(bookId: string, patch: { title?: string; author?: string | null }): Promise<Book> {
    return request(`/books/${bookId}`, json("PATCH", patch));
  }

  deleteBook(bookId: string): Promise<void> {
    return request(`/books/${bookId}`, { method: "DELETE" });
  }

  saveLastPage(bookId: string, page: number): Promise<void> {
    return request(`/books/${bookId}/last-page`, json("PUT", { page }));
  }

  askQuestion(bookId: string, question: string): Promise<{ answer: string }> {
    return request(`/books/${bookId}/ask`, json("POST", { question }));
  }

  async getChatAvailability(): Promise<ChatAvailability> {
    try {
      return (await request<{ availability: ChatAvailability }>("/chat/availability")).availability;
    } catch {
      return "unavailable";
    }
  }

  onBookProgress(bookId: string, cb: (p: BookProgress) => void): () => void {
    this.connect();
    if (!this.progressListeners.has(bookId)) this.progressListeners.set(bookId, new Set());
    this.progressListeners.get(bookId)!.add(cb);
    return () => this.progressListeners.get(bookId)?.delete(cb);
  }

  onLibraryChange(cb: () => void): () => void {
    this.connect();
    this.libraryListeners.add(cb);
    return () => this.libraryListeners.delete(cb);
  }
}
