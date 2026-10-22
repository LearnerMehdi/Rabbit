/**
 * The contract between the UI and the backend: exactly the actions in the
 * design system's "Action annotations" table, plus small helpers the UI needs
 * (library change events, chat availability).
 *
 * Today only the mock implementation exists (src/api/mock.ts). The HTTP client
 * for the backend will implement this same interface.
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
  /** first-page thumbnail (data URL); the backend will serve this as an image URL */
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
  /** the PDF bytes; the backend will serve a URL instead */
  file: Blob;
}

export type ChatAvailability = "available" | "unavailable";

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
  askQuestion(bookId: string, question: string): Promise<{ answer: string }>;
  getChatAvailability(): Promise<ChatAvailability>;

  /** progress of one book; returns an unsubscribe function */
  onBookProgress(bookId: string, cb: (p: BookProgress) => void): () => void;
  /** any book added, changed or removed */
  onLibraryChange(cb: () => void): () => void;
}
