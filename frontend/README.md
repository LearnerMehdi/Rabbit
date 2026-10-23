# Orange Reader — frontend

React + TypeScript (Vite) UI for the Orange Reader library and reader, built from the
Orange Reader design system (`design/tokens.json`, `src/styles/ds.css`, brand book in
`design/README.md`).

Every backend action goes through one interface, `LibraryApi` (`src/api/types.ts`), the
actions listed in the design system's *Action annotations* table. It is implemented by
`src/api/http.ts` against the backend (`backend/api/app.py`) on the same origin; progress
and library changes arrive as server-sent events on `/api/events`.

PDFs are fetched from the backend and rendered in the browser with pdf.js (pages,
thumbnails, search in book). Chat messages are kept in memory per book while the app is
open and are gone after a reload; each question is sent on its own.

## Run

The app is started from the project root with `./start.sh`, which builds this frontend
and serves it with the backend at http://127.0.0.1:8000. For work on the frontend alone:

```bash
npm test           # unit tests for the HTTP client and formatting
npm run typecheck
npm run build      # what start.sh runs; also regenerates src/styles/tokens.css
```

## Layout

```
design/            design-system tokens.json + brand book (source of truth)
scripts/tokens.mjs tokens.json -> src/styles/tokens.css
src/api/           LibraryApi contract and its HTTP client
src/pdf/           pdf.js helpers (load, inspect, cover)
src/components/    BookCard, Menu, Dialog, AddBookDialog, PdfPages, Thumbnails, ChatPanel, …
src/screens/       Library, Reader
tests/             vitest
```
