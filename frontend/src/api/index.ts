import { inspectPdf } from "../pdf/pdf";
import { MockApi } from "./mock";
import type { LibraryApi } from "./types";

export * from "./types";

/**
 * The one API instance the UI uses. Only the mock exists for now: the UI never
 * talks to the backend. When the backend endpoints exist, add an HTTP client
 * implementing LibraryApi and pick it here (e.g. VITE_API_MODE=http).
 */
export const mockApi = new MockApi(inspectPdf);
export const api: LibraryApi = mockApi;
