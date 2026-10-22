/**
 * In-browser stand-in for the backend. No network: books and PDFs live in
 * IndexedDB, preparation is simulated with the backend's stages and timing,
 * and chat answers according to the dev-panel chat mode ("unavailable" by default).
 */
import { Idb } from "./idb";
import { getSettings, setSettings } from "./settings";
import {
  ApiError,
  type Book,
  type BookProgress,
  type ChatAvailability,
  type LibraryApi,
  type OpenedBook,
  type SortKey,
} from "./types";

/** What the mock needs to know about a PDF; in the app this comes from pdf.js. */
export interface PdfFacts {
  pageCount: number;
  encrypted: boolean;
  /** more than 80% of pages without a text layer (backend fails these) */
  needsOcr: boolean;
  cover: string | null;
}

export type PdfInspector = (file: Blob) => Promise<PdfFacts>;

// Overall percent at which each backend stage starts (backend/ingest/pipeline.py).
const STAGES: [string, number][] = [
  ["extracting", 0],
  ["chunking", 10],
  ["embedding", 20],
  ["saving", 90],
];
// Backend baseline: ~16 pages/s on the dev GPU, plus fixed overhead.
const MS_PER_PAGE = 60;
const MIN_MS = 2500;
const TICK_MS = 200;

export const CHAT_UNAVAILABLE = "Chat is unavailable right now.";

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

function stageAt(percent: number): string {
  let stage = STAGES[0][0];
  for (const [name, start] of STAGES) if (percent >= start) stage = name;
  return stage;
}

async function sha256(file: Blob): Promise<string> {
  const buf = await file.arrayBuffer();
  const digest = await crypto.subtle.digest("SHA-256", buf);
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

async function isPdf(file: Blob): Promise<boolean> {
  const head = new Uint8Array(await file.slice(0, 1024).arrayBuffer());
  const text = String.fromCharCode(...head);
  return text.includes("%PDF-");
}

interface StoredBook extends Book {
  sha256: string;
}

export class MockApi implements LibraryApi {
  private db: Idb;
  private jobs = new Map<string, { cancelled: boolean }>();
  private progressListeners = new Map<string, Set<(p: BookProgress) => void>>();
  private libraryListeners = new Set<() => void>();
  private ready: Promise<void>;

  constructor(
    private inspect: PdfInspector,
    opts: { dbName?: string } = {},
  ) {
    this.db = new Idb(opts.dbName);
    this.ready = this.resumeJobs();
  }

  // --- helpers -----------------------------------------------------------------

  private async latency() {
    const ms = getSettings().latencyMs;
    if (ms > 0) await sleep(ms);
  }

  private async load(bookId: string): Promise<StoredBook> {
    const book = await this.db.get<StoredBook>("books", bookId);
    if (!book) throw new ApiError("not_found", "This book is no longer in your library.");
    return book;
  }

  private async save(book: StoredBook): Promise<void> {
    await this.db.put("books", book);
    this.emit(book);
  }

  private emit(book: Book | null, bookId?: string) {
    if (book) {
      const p: BookProgress = { percent: book.percent, status: book.status, stage: book.stage, error: book.error };
      this.progressListeners.get(book.id)?.forEach((cb) => cb(p));
    } else if (bookId) {
      this.progressListeners.delete(bookId);
    }
    this.libraryListeners.forEach((cb) => cb());
  }

  private publicBook({ sha256: _sha, ...book }: StoredBook): Book {
    return book;
  }

  /** Books left "indexing" by a reload pick up where they were. */
  private async resumeJobs() {
    const books = await this.db.all<StoredBook>("books");
    for (const b of books) if (b.status === "indexing") this.startJob(b.id);
  }

  private startJob(bookId: string) {
    const prev = this.jobs.get(bookId);
    if (prev) prev.cancelled = true; // a re-index replaces the running job
    const job = { cancelled: false };
    this.jobs.set(bookId, job);
    void this.runJob(bookId, job);
  }

  private async runJob(bookId: string, job: { cancelled: boolean }) {
    // consumed by the first job that starts after it was set
    const fail = getSettings().failNext;
    if (fail) setSettings({ failNext: false });
    let book: StoredBook;
    try {
      book = await this.load(bookId);
      const file = await this.db.get<Blob>("files", bookId);
      if (!file) throw new ApiError("failed", "Source file is missing");
      const facts = await this.inspect(file);
      book.pageCount = facts.pageCount;
      book.cover = book.cover ?? facts.cover;

      const totalMs = Math.max(MIN_MS, facts.pageCount * MS_PER_PAGE);
      let percent = book.percent;
      while (percent < 100) {
        await sleep(TICK_MS);
        if (job.cancelled) return;
        const speed = Math.max(0.1, getSettings().speed);
        percent = Math.min(100, percent + (100 * TICK_MS * speed) / totalMs);
        const stage = stageAt(percent);

        // the same failure points as the backend
        if (facts.encrypted && stage !== "extracting") throw new ApiError("failed", "PDF is password-protected");
        if (facts.needsOcr && percent >= 10) throw new ApiError("failed", "No text layer (scanned PDF)");
        if (fail && percent >= 50) throw new ApiError("failed", "Simulated failure (mock backend)");

        book = { ...(await this.load(bookId)), percent: Math.floor(percent), stage, pageCount: book.pageCount, cover: book.cover };
        if (percent >= 100) {
          book = { ...book, status: "ready", percent: 100, stage: null, error: null };
        }
        await this.save(book);
      }
    } catch (e) {
      if (job.cancelled) return;
      if (e instanceof ApiError && e.code === "not_found") return; // deleted meanwhile
      try {
        const current = await this.load(bookId);
        await this.save({ ...current, status: "failed", stage: null, error: e instanceof Error ? e.message : String(e) });
      } catch {
        /* deleted meanwhile */
      }
    } finally {
      if (this.jobs.get(bookId) === job) this.jobs.delete(bookId);
    }
  }

  // --- LibraryApi --------------------------------------------------------------

  async listBooks({ query = "", sort = "added" }: { query?: string; sort?: SortKey } = {}): Promise<Book[]> {
    await this.ready;
    await this.latency();
    const q = query.trim().toLowerCase();
    let books = (await this.db.all<StoredBook>("books")).map((b) => this.publicBook(b));
    if (q) books = books.filter((b) => `${b.title} ${b.author ?? ""}`.toLowerCase().includes(q));
    const cmp: Record<SortKey, (a: Book, b: Book) => number> = {
      title: (a, b) => a.title.localeCompare(b.title, undefined, { sensitivity: "base" }),
      added: (a, b) => b.createdAt - a.createdAt,
      opened: (a, b) => (b.lastOpenedAt ?? 0) - (a.lastOpenedAt ?? 0) || b.createdAt - a.createdAt,
    };
    return books.sort(cmp[sort]);
  }

  async addBook(file: File, meta: { title: string; author?: string | null }): Promise<Book> {
    await this.ready;
    await this.latency();
    if (!(await isPdf(file))) throw new ApiError("not_pdf", "This file isn't a PDF. Choose a .pdf file.");
    const digest = await sha256(file);
    const books = await this.db.all<StoredBook>("books");
    if (books.some((b) => b.sha256 === digest)) {
      throw new ApiError("duplicate", "This book is already in your library.");
    }
    const book: StoredBook = {
      id: crypto.randomUUID(),
      title: meta.title.trim(),
      author: meta.author?.trim() || null,
      fileName: file.name,
      fileSize: file.size,
      pageCount: null,
      status: "indexing",
      percent: 0,
      stage: "extracting",
      error: null,
      createdAt: Date.now(),
      lastOpenedAt: null,
      lastPage: 1,
      cover: null,
      sha256: digest,
    };
    await this.db.put("files", file, book.id);
    await this.save(book);
    this.startJob(book.id);
    return this.publicBook(book);
  }

  async reindexBook(bookId: string): Promise<void> {
    await this.latency();
    const book = await this.load(bookId);
    await this.save({ ...book, status: "indexing", percent: 0, stage: "extracting", error: null });
    this.startJob(bookId);
  }

  async openBook(bookId: string): Promise<OpenedBook> {
    await this.latency();
    const book = await this.load(bookId);
    const file = await this.db.get<Blob>("files", bookId);
    if (!file) throw new ApiError("not_found", "The PDF for this book is missing.");
    const updated = { ...book, lastOpenedAt: Date.now() };
    await this.db.put("books", updated);
    this.libraryListeners.forEach((cb) => cb());
    return { book: this.publicBook(updated), file };
  }

  async updateBook(bookId: string, patch: { title?: string; author?: string | null }): Promise<Book> {
    await this.latency();
    const book = await this.load(bookId);
    const title = patch.title?.trim();
    const updated: StoredBook = {
      ...book,
      ...(title ? { title } : {}),
      ...(patch.author !== undefined ? { author: patch.author?.trim() || null } : {}),
    };
    await this.save(updated);
    return this.publicBook(updated);
  }

  async deleteBook(bookId: string): Promise<void> {
    await this.latency();
    const job = this.jobs.get(bookId);
    if (job) job.cancelled = true;
    await this.db.delete("books", bookId);
    await this.db.delete("files", bookId);
    this.emit(null, bookId);
  }

  async saveLastPage(bookId: string, page: number): Promise<void> {
    const book = await this.db.get<StoredBook>("books", bookId);
    if (book && book.lastPage !== page) await this.db.put("books", { ...book, lastPage: page });
  }

  async getChatAvailability(): Promise<ChatAvailability> {
    return getSettings().chatMode === "unavailable" ? "unavailable" : "available";
  }

  async askQuestion(bookId: string, question: string): Promise<{ answer: string }> {
    const book = await this.load(bookId);
    await sleep(Math.max(600, getSettings().latencyMs));
    if (book.status !== "ready") throw new ApiError("not_ready", "This book is still being prepared.");
    switch (getSettings().chatMode) {
      case "unavailable":
        throw new ApiError("unavailable", CHAT_UNAVAILABLE);
      case "error":
        throw new ApiError("failed", "Couldn't get an answer. Try again.");
      case "echo":
        return {
          answer:
            `This is a mock answer about "${book.title}". The assistant isn't connected yet.\n\n` +
            `You asked: ${question.trim()}`,
        };
    }
  }

  onBookProgress(bookId: string, cb: (p: BookProgress) => void): () => void {
    if (!this.progressListeners.has(bookId)) this.progressListeners.set(bookId, new Set());
    this.progressListeners.get(bookId)!.add(cb);
    return () => this.progressListeners.get(bookId)?.delete(cb);
  }

  onLibraryChange(cb: () => void): () => void {
    this.libraryListeners.add(cb);
    return () => this.libraryListeners.delete(cb);
  }

  /** dev panel: wipe the mock library */
  async reset(): Promise<void> {
    this.jobs.forEach((j) => (j.cancelled = true));
    this.jobs.clear();
    await this.db.clear();
    this.libraryListeners.forEach((cb) => cb());
  }
}
