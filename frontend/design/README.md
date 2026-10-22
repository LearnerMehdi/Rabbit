Orange Reader is a desktop digital library and PDF reader for scientific and technical books, with a plain AI chat panel beside the page. The interface is light, calm and document-first, laid out like a familiar PDF reader: white and light grey everywhere, the book in the middle, and **one orange accent** that marks what you can do next. Build every screen from the tokens and components here; the product's own backend is out of scope — controls only call the actions listed under *Action annotations* and react to what comes back.

## Content and voice

- Plain, short and calm. Say what is happening, not how. No emoji, no exclamation marks, no jokes in system messages.
- Sentence case everywhere: "Add book", "Add to library", "Date added".
- Buttons start with a verb and name the result: **Add to library**, **Delete**, **Confirm**. Never "OK" or "Submit".
- Use the ellipsis character `…`, never three dots: "Preparing…".
- Numbers as digits, with "of" in prose and a slash in the status bar: "Page 112 of 775" on a card, "112 / 775" in the reader.
- Address the person as "you" only when needed; most strings need no pronoun.
- Use these strings exactly:

| Where | String |
| --- | --- |
| Empty library | Your library is empty |
| Card while preparing | Preparing… 42% |
| Card states | Ready · Failed · Retry |
| Chat input while preparing | Preparing this book… 42% |
| Empty chat | Ask anything about this book. |
| Failed answer | Couldn't get an answer. Try again. |
| Delete dialog | Delete '{title}'? This removes the book and its data. |
| Re-index dialog | Re-index '{title}'? The book is prepared again from the PDF. Reading still works; chat is paused until it's ready. |
| Add book errors | This file isn't a PDF. Choose a .pdf file. · This book is already in your library. |

## Colour

- Set every surface in `bg` (panels, cards, dialogs, PDF pages) or `bg-subtle` (thumbnail sidebar, the surround behind PDF pages, the chat input, card cover areas). Separate regions with a 1px `border` line, not with shade alone.
- **Orange is the only accent.** Use `accent` as a fill for the one primary action in a view (Add book, Add to library, Send), the progress-bar fill, and nothing larger than a button. Never paint a header, panel or sidebar orange.
- Labels on orange fills are `on-accent` (dark ink): white on `#F57C00` is 2.7:1 and fails WCAG AA.
- Orange text and icons — links like **Retry**, the active page number, an active toolbar icon — use `accent-text` (4.94:1). Orange strokes — focus rings, the active thumbnail outline, a dragged-over drop zone — use `accent-line`.
- `accent-soft` marks selection: the user's question bubble, the selected menu row, the chat toggle when the panel is open, the Preparing badge. Put `text` on it, never `text-muted`.
- Status colours only ever mean status and always travel with a word: Ready is `success-strong` on `success-soft` with a check; Failed is `danger-strong` on `danger-soft` with an alert icon. Delete and errors use `danger`; the Delete button is `danger` with `on-danger`.
- Edges of controls (inputs, secondary buttons, steppers, the drop zone) are `border-control` (3:1); `border` is for decorative dividers and card outlines.
- Dialogs sit on the `overlay` scrim.

## Type

- Inter, falling back to the system UI face (`--font-sans`). 14px is the UI base.
- `title-lg` for the library title and the Add book dialog; `title` for confirmation dialogs; `body` for copy, menus and inputs; `label` for buttons, field labels and links; `card-title` for book titles (two lines, then clamp); `caption` for authors, progress, percentages and the status bar; `badge` for badges.
- Everything in the chat — questions, answers and what you type — is `chat`: 15px, 1.6 line height.
- `annotation` (mono) is only for developer annotations in design files.

## Space, shape and depth

- Spacing steps are `space-1` 4 · `space-2` 8 · `space-3` 12 · `space-4` 16 · `space-6` 24 · `space-8` 32. Library margins `space-8`, grid gap `space-6`, card body `space-3`, dialog padding `space-6`, chat message gap `space-4`.
- Corners are `radius` (8px) on cards, buttons, inputs, menus, dialogs and the chat bubble; `radius-sm` on menu rows and small chips; `radius-pill` on badges and the progress bar. PDF pages have square corners.
- Borders separate; shadows only lift things that float: `shadow-page` under PDF pages and thumbnails, `shadow-menu` under menus and a hovered card, `shadow-dialog` under dialogs.

## Layout

- Desktop first at 1440×900. The reader must still work at 1280×800 with the chat panel open.
- Library: a `header-height` header (app name, search, sort, **Add book**), then a grid that auto-fills `card-width` columns with `space-6` gaps inside `space-8` margins — 5 columns at 1440, 4–5 at 1280. New books appear first.
- Reader: `topbar-height` top bar → thumbnail sidebar (`sidebar-width`, collapsible) | PDF pages on `bg-subtle`, continuous vertical scroll, `space-6` between pages | chat panel (`chat-panel-width`, draggable between `chat-panel-min` and `chat-panel-max`, collapsible) → `statusbar-height` status bar with "page X / Y".
- At 1280 with both side panels open the page column is 680px: default the zoom to *fit width* there, and let the person collapse the thumbnails.
- The chat panel holds only three things: the message list, the thinking indicator and the input. No citations, sources, suggested prompts, history, attachments or selection toolbar.

## States

- Hover: secondary and ghost controls take `bg-subtle`; primary takes `accent-hover`; cards gain `border-control` and `shadow-menu`.
- Focus: a solid 2px `accent-line` ring, offset 2px, on every focusable element (inputs show it as border + 1px ring). Never remove it.
- Disabled: `bg-subtle` fill, `border` edge, `text-disabled` label, no hover.
- Preparing: the card shows a progress bar and "Preparing… N%"; the book can be opened and read; the chat input is replaced by the note "Preparing this book… N%". On *ready* the badge turns green and the input unlocks; on *failed* the red badge and **Retry** appear.
- Errors sit right under what failed, in `danger`, in one sentence that says what to do.

## Motion

- Colour and border transitions 120ms; the progress-bar fill eases over 200ms.
- The thinking indicator pulses three dots (1.2s loop); the preparing spinner turns once every 900ms. Both stop under `prefers-reduced-motion`.
- No slide-ins, bounces or page transitions.

## Iconography

- 16px line icons, 1.75px stroke, round caps and joins, drawn in `currentColor` (`.or-icon`). Icons sit beside a label; icon-only buttons (zoom, chat toggle, ⋯, send) carry an `aria-label` and a tooltip.
- The brief names no icon set, so the components draw Lucide-style outlines (search, more-horizontal, chevrons, plus, minus, arrow-up, panel-left, panel-right, check, alert-circle, upload, file, trash, refresh). *Substitute — swap for the product's chosen set when there is one.*
- No logo exists yet: the app name is set in `title` type in `text`.

## Action annotations

Design files label each control that triggers backend work with an `.or-annot` chip (`annotation` style, dashed `border-control`) naming the exact action it calls. The UI only calls these and reacts:

| Control | Action called | UI result |
| --- | --- | --- |
| Add to library | `addBook(file, {title, author})` | New card first in the grid, "Preparing… 0%" |
| (background) | `onBookProgress(bookId, {percent, status})` | Bar updates; `ready` → green badge, chat unlocks; `failed` → red badge + Retry |
| Retry / Re-index | `reindexBook(bookId)` | Card back to "Preparing… 0%" |
| Card click / Open | `openBook(bookId)` | Reader opens at the last-read page |
| Rename | `updateBook(bookId, {title})` | Card updates in place |
| Delete | `deleteBook(bookId)` | Card removed after confirmation |
| Library search / sort | `listBooks({query, sort})` | Grid filters and re-orders |
| Page change (scroll) | `saveLastPage(bookId, page)` | No visible change |
| Send (chat) | `askQuestion(bookId, question)` → `answer` | Question, thinking indicator, then the answer |
