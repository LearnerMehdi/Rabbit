import { HttpApi } from "./http";
import type { LibraryApi } from "./types";

export * from "./types";

/** The one API instance the UI uses: the backend, served from the same origin. */
export const api: LibraryApi = new HttpApi();
