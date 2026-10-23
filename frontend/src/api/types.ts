/**
 * The contract between the UI and the backend: exactly the actions in the
 * design system's "Action annotations" table, plus small helpers the UI needs
 * (library change events, chat availability).
 *
 * Implemented by the HTTP client (src/api/http.ts) for backend/api/app.py.
 */

export type BookStatus = "indexing" | "ready" | "failed";
export type SortKey = "title" | "added" | "opened";

export interface Book {
  id: string;
  title: string;
  author: string | null;
  fileName: string;
  fileSize: number;
  pageCount: number | null;
  status: BookStatus;
  /** 0–100 while status is "indexing" */
  percent: number;
  /** backend stage while indexing: extracting | chunking | embedding | saving */
  stage: string | null;
  error: string | null;
  createdAt: number;
  lastOpenedAt: number | null;
  lastPage: number;
  /** first-page thumbnail URL served by the backend */
  cover: string | null;
}

export interface BookProgress {
  percent: number;
  status: BookStatus;
  stage: string | null;
  error: string | null;
}

export interface OpenedBook {
  book: Book;
  /** the PDF bytes, fetched from the backend */
  file: Blob;
}

/** Where a retrieved excerpt is on one page: line boxes as fractions of the page, origin top-left. */
export interface Highlight {
  page: number;
  rects: [number, number, number, number][];
}

/** One excerpt retrieved for an answer, for the UI only (the LLM never sees these). */
export interface Source {
  /** 1-based, closest to the question first */
  n: number;
  pageStart: number;
  pageEnd: number;
  /** cosine similarity between the question and the excerpt, 0–1 */
  similarity: number;
  text: string;
  highlights: Highlight[];
}

export interface AnswerResult {
  answer: string;
  sources: Source[];
}

export type ChatAvailability = "available" | "unavailable";

export const CHAT_UNAVAILABLE = "Chat is unavailable right now.";

export type ApiErrorCode = "not_pdf" | "duplicate" | "not_found" | "not_ready" | "unavailable" | "failed";

export class ApiError extends Error {
  constructor(
    public code: ApiErrorCode,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export interface LibraryApi {
  listBooks(opts?: { query?: string; sort?: SortKey }): Promise<Book[]>;
  addBook(file: File, meta: { title: string; author?: string | null }): Promise<Book>;
  reindexBook(bookId: string): Promise<void>;
  openBook(bookId: string): Promise<OpenedBook>;
  updateBook(bookId: string, patch: { title?: string; author?: string | null }): Promise<Book>;
  deleteBook(bookId: string): Promise<void>;
  saveLastPage(bookId: string, page: number): Promise<void>;
  askQuestion(bookId: string, question: string): Promise<AnswerResult>;
  getChatAvailability(): Promise<ChatAvailability>;

  /** progress of one book; returns an unsubscribe function */
  onBookProgress(bookId: string, cb: (p: BookProgress) => void): () => void;
  /** any book added, changed or removed */
  onLibraryChange(cb: () => void): () => void;
}
