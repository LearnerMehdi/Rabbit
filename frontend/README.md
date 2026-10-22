# Orange Reader — frontend

React + TypeScript (Vite) UI for the Orange Reader library and reader, built from the
Orange Reader design system (`design/tokens.json`, `src/styles/ds.css`, brand book in
`design/README.md`).

**It does not talk to the backend.** Every backend action goes through one interface,
`LibraryApi` (`src/api/types.ts`) — the actions listed in the design system's
*Action annotations* table — and today the only implementation is an in-browser mock
(`src/api/mock.ts`):

| Action | Mock behaviour |
| --- | --- |
| `addBook(file, {title, author})` | rejects non-PDFs and duplicates (SHA-256, like the backend); stores the PDF in IndexedDB |
| `onBookProgress(bookId, …)` | simulated preparation with the backend's stages (extracting → chunking → embedding → saving) at ~16 pages/s; scanned PDFs fail with "No text layer (scanned PDF)" |
| `reindexBook`, `updateBook`, `deleteBook`, `listBooks`, `openBook`, `saveLastPage` | IndexedDB; nothing leaves the browser |
| `askQuestion(bookId, question)` | **chat is unavailable by default**; the dev panel can switch it to mock answers or failures |

PDFs are really opened and rendered in the browser with pdf.js (pages, thumbnails,
covers, search in book), so reading works without any backend.

## Run

```bash
npm install
npm run dev        # http://localhost:5173
npm test           # unit tests for the mock API
npm run build      # typecheck + production build
```

`npm run dev`/`build` regenerate `src/styles/tokens.css` from `design/tokens.json`.

## Mock backend panel

The dashed **mock backend** chip (bottom left) opens the simulation controls: chat mode
(unavailable / mock reply / always fails), preparation speed, latency per call,
"fail the next preparation", and clearing the mock library. It is a test harness, not
product UI, and goes away with the mock.

## Connecting the backend later

Write an HTTP client implementing `LibraryApi` and choose it in `src/api/index.ts`.
The UI only depends on that interface. Two places assume the mock and will change:
`OpenedBook.file` (a Blob today; a URL from the backend) and `Book.cover` (a data URL today).

## Layout

```
design/            design-system tokens.json + brand book (source of truth)
scripts/tokens.mjs tokens.json -> src/styles/tokens.css
src/api/           LibraryApi contract, mock implementation, IndexedDB, mock settings
src/pdf/           pdf.js helpers (load, inspect, cover)
src/components/    BookCard, Menu, Dialog, AddBookDialog, PdfPages, Thumbnails, ChatPanel, …
src/screens/       Library, Reader
src/dev/           mock backend panel
tests/             vitest
```
