import type { PDFDocumentProxy } from "pdfjs-dist";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, type Book } from "../api";
import { ChatPanel, pagesLabel, type SourceFocus } from "../components/ChatPanel";
import { Icon } from "../components/Icon";
import { PdfPages, usePageSizes, PT_TO_PX, type PageMark, type PdfPagesHandle } from "../components/PdfPages";
import { Thumbnails } from "../components/Thumbnails";
import { useThrottled } from "../lib/hooks";
import { loadPdf } from "../pdf/pdf";

const ZOOM_MIN = 0.5;
const ZOOM_MAX = 4;
const CHAT_MIN = 320;
const CHAT_MAX = 560;

type ZoomMode = "fit" | number;

function usePersisted<T>(key: string, initial: T): [T, (v: T) => void] {
  const [v, setV] = useState<T>(() => {
    try {
      const raw = localStorage.getItem(key);
      return raw === null ? initial : (JSON.parse(raw) as T);
    } catch {
      return initial;
    }
  });
  const set = (next: T) => {
    setV(next);
    try {
      localStorage.setItem(key, JSON.stringify(next));
    } catch {
      /* fine */
    }
  };
  return [v, set];
}

/** Search in book: page text from pdf.js, matches counted per page. */
function useBookSearch(doc: PDFDocumentProxy | null) {
  const texts = useRef<string[] | null>(null);
  const [state, setState] = useState<{ query: string; hits: number[]; index: number; searching: boolean }>({
    query: "",
    hits: [],
    index: 0,
    searching: false,
  });

  const run = async (query: string): Promise<number | null> => {
    const q = query.trim().toLowerCase();
    if (!doc || !q) {
      setState({ query, hits: [], index: 0, searching: false });
      return null;
    }
    setState((s) => ({ ...s, query, searching: true }));
    if (!texts.current) {
      const all: string[] = [];
      for (let i = 1; i <= doc.numPages; i++) {
        const content = await (await doc.getPage(i)).getTextContent();
        all.push(content.items.map((it) => ("str" in it ? it.str : "")).join(" ").toLowerCase());
      }
      texts.current = all;
    }
    // one hit per occurrence, recorded as its page number
    const hits: number[] = [];
    texts.current.forEach((t, i) => {
      let at = t.indexOf(q);
      while (at !== -1) {
        hits.push(i + 1);
        at = t.indexOf(q, at + q.length);
      }
    });
    setState({ query, hits, index: 0, searching: false });
    return hits[0] ?? null;
  };

  const step = (delta: number): number | null => {
    if (!state.hits.length) return null;
    const index = (state.index + delta + state.hits.length) % state.hits.length;
    setState((s) => ({ ...s, index }));
    return state.hits[index];
  };

  return { ...state, run, step };
}

export function Reader({ bookId, onBack }: { bookId: string; onBack: () => void }) {
  const [book, setBook] = useState<Book | null>(null);
  const [doc, setDoc] = useState<PDFDocumentProxy | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [pageInput, setPageInput] = useState("1");
  const [zoomMode, setZoomMode] = usePersisted<ZoomMode>("or-zoom", "fit");
  const [fitZoom, setFitZoom] = useState(1);
  const [thumbsOpen, setThumbsOpen] = usePersisted("or-thumbs-open", true);
  const [chatOpen, setChatOpen] = usePersisted("or-chat-open", true);
  const [chatWidth, setChatWidth] = usePersisted("or-chat-width", 380);
  const [searchOpen, setSearchOpen] = useState(false);
  const [searchDraft, setSearchDraft] = useState("");
  // the sources of one answer, highlighted in the book; optionally only their pages are shown
  const [focus, setFocus] = useState<SourceFocus | null>(null);
  const [onlySources, setOnlySources] = useState(false);
  const pages = useRef<PdfPagesHandle>(null);
  const searchInput = useRef<HTMLInputElement>(null);
  const restored = useRef(false);
  const sizes = usePageSizes(doc);
  const search = useBookSearch(doc);

  // open the book
  useEffect(() => {
    let cancelled = false;
    let loaded: PDFDocumentProxy | null = null;
    (async () => {
      try {
        const { book, file } = await api.openBook(bookId);
        if (cancelled) return;
        setBook(book);
        loaded = await loadPdf(file);
        if (cancelled) return void loaded.destroy();
        setDoc(loaded);
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : "Couldn't open this book.");
      }
    })();
    return () => {
      cancelled = true;
      void loaded?.destroy();
    };
  }, [bookId]);

  // keep book metadata (title, status) live
  useEffect(
    () =>
      api.onLibraryChange(async () => {
        const all = await api.listBooks();
        const b = all.find((x) => x.id === bookId);
        if (b) setBook(b);
        else onBack(); // deleted
      }),
    [bookId, onBack],
  );

  const computeFit = useCallback(() => {
    if (!sizes.length || !pages.current) return;
    const w = pages.current.availableWidth();
    const widest = Math.max(...sizes.slice(0, 20).map((s) => s.w));
    setFitZoom(Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, w / (widest * PT_TO_PX))));
  }, [sizes]);

  useEffect(computeFit, [computeFit, thumbsOpen, chatOpen, chatWidth]);

  const zoom = zoomMode === "fit" ? fitZoom : zoomMode;

  // open at the last-read page once the layout exists
  useEffect(() => {
    if (restored.current || !sizes.length || !book) return;
    restored.current = true;
    const target = Math.min(book.lastPage || 1, sizes.length);
    requestAnimationFrame(() => pages.current?.scrollToPage(target));
  }, [sizes.length, book]);

  const saveLastPage = useThrottled((p: number) => void api.saveLastPage(bookId, p), 1000);

  const onPageChange = useCallback(
    (p: number) => {
      setPage(p);
      setPageInput(String(p));
      if (restored.current) saveLastPage(p);
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [],
  );

  const goTo = (p: number) => {
    if (!sizes.length) return;
    const target = Math.min(Math.max(1, Math.round(p)), sizes.length);
    pages.current?.scrollToPage(target);
    setPageInput(String(target));
  };

  const stepZoom = (dir: 1 | -1) => {
    const z = Math.round((zoom + dir * 0.1) * 10) / 10;
    setZoomMode(Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, z)));
  };

  // drag the chat panel's left edge
  const startResize = (e: React.PointerEvent) => {
    e.preventDefault();
    const startX = e.clientX;
    const startW = chatWidth;
    const move = (ev: PointerEvent) =>
      setChatWidth(Math.min(CHAT_MAX, Math.max(CHAT_MIN, startW + (startX - ev.clientX))));
    const up = () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
      document.body.classList.remove("is-resizing");
    };
    document.body.classList.add("is-resizing");
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
  };

  useEffect(() => {
    if (searchOpen) searchInput.current?.focus();
  }, [searchOpen]);

  const marks = useMemo<PageMark[]>(
    () =>
      focus?.sources.flatMap((s) =>
        s.highlights.map((h) => ({ page: h.page, n: s.n, rects: h.rects, active: s.n === focus.n })),
      ) ?? [],
    [focus],
  );

  const sourcePages = useMemo(() => {
    if (!focus || !onlySources) return null;
    const all = focus.sources.flatMap((s) =>
      s.highlights.length
        ? s.highlights.map((h) => h.page)
        : Array.from({ length: s.pageEnd - s.pageStart + 1 }, (_, i) => s.pageStart + i),
    );
    return [...new Set(all)].sort((a, b) => a - b);
  }, [focus, onlySources]);

  // scroll to the shown source: the top of its first highlighted line, or its first page
  const focusKey = focus && `${focus.answerId}:${focus.n}:${onlySources}`;
  useEffect(() => {
    if (!focus) return;
    const src = focus.sources.find((s) => s.n === focus.n);
    if (!src) return;
    const first = src.highlights[0];
    requestAnimationFrame(() => {
      if (first) pages.current?.scrollToPage(first.page, Math.max(0, Math.min(...first.rects.map((r) => r[1])) - 0.02));
      else pages.current?.scrollToPage(src.pageStart);
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [focusKey]);

  const stepSource = (delta: number) => {
    if (!focus) return;
    const count = focus.sources.length;
    setFocus({ ...focus, n: ((focus.n - 1 + delta + count) % count) + 1 });
  };
  const shown = focus?.sources.find((s) => s.n === focus.n);

  if (error) {
    return (
      <div className="or app-reader">
        <div className="or-toolbar">
          <button type="button" className="or-btn or-btn--ghost app-back" onClick={onBack}>
            <Icon name="chevronLeft" />
            Library
          </button>
        </div>
        <div className="app-empty">
          <p className="or-error">{error}</p>
        </div>
      </div>
    );
  }

  const total = doc?.numPages ?? book?.pageCount ?? 0;

  return (
    <div className="or app-reader">
      <div className="or-toolbar">
        <button type="button" className="or-btn or-btn--ghost app-back" onClick={onBack}>
          <Icon name="chevronLeft" />
          Library
        </button>
        <div className="or-vr" />
        <button
          type="button"
          className={`or-btn or-btn--ghost or-btn--icon${thumbsOpen ? " is-active" : ""}`}
          aria-label={thumbsOpen ? "Hide thumbnails" : "Show thumbnails"}
          title={thumbsOpen ? "Hide thumbnails" : "Show thumbnails"}
          aria-pressed={thumbsOpen}
          onClick={() => setThumbsOpen(!thumbsOpen)}
        >
          <Icon name="panelLeft" />
        </button>
        {searchOpen ? (
          <form
            className="app-search"
            onSubmit={async (e) => {
              e.preventDefault();
              if (searchDraft !== search.query) {
                const p = await search.run(searchDraft);
                if (p) goTo(p);
              } else {
                const p = search.step(1);
                if (p) goTo(p);
              }
            }}
            onKeyDown={(e) => {
              if (e.key === "Escape") {
                setSearchOpen(false);
                void search.run("");
              }
            }}
          >
            <div className="or-search app-search__field">
              <Icon name="search" />
              <input
                ref={searchInput}
                className="or-input"
                placeholder="Search in book"
                aria-label="Search in book"
                value={searchDraft}
                onChange={(e) => setSearchDraft(e.target.value)}
              />
            </div>
            <span className="or-cap app-search__count" aria-live="polite">
              {search.searching
                ? "Searching…"
                : search.query
                  ? search.hits.length
                    ? `${search.index + 1} of ${search.hits.length}`
                    : "No matches"
                  : ""}
            </span>
            <button
              type="button"
              className="or-btn or-btn--ghost or-btn--icon"
              aria-label="Previous match"
              title="Previous match"
              disabled={!search.hits.length}
              onClick={() => {
                const p = search.step(-1);
                if (p) goTo(p);
              }}
            >
              <Icon name="chevronUp" />
            </button>
            <button
              type="button"
              className="or-btn or-btn--ghost or-btn--icon"
              aria-label="Next match"
              title="Next match"
              disabled={!search.hits.length}
              onClick={() => {
                const p = search.step(1);
                if (p) goTo(p);
              }}
            >
              <Icon name="chevronDown" />
            </button>
            <button
              type="button"
              className="or-btn or-btn--ghost or-btn--icon"
              aria-label="Close search"
              title="Close search"
              onClick={() => {
                setSearchOpen(false);
                void search.run("");
              }}
            >
              <Icon name="close" />
            </button>
          </form>
        ) : (
          <>
            <div className="or-toolbar__title" title={book?.title}>
              {book?.title}
            </div>
            <button
              type="button"
              className="or-btn or-btn--ghost or-btn--icon"
              aria-label="Search in book"
              title="Search in book"
              onClick={() => setSearchOpen(true)}
            >
              <Icon name="search" />
            </button>
          </>
        )}
        <div className="or-vr" />
        <div className="or-stepper">
          <button
            type="button"
            className="or-btn or-btn--ghost or-btn--icon"
            aria-label="Zoom out"
            title="Zoom out"
            disabled={zoom <= ZOOM_MIN}
            onClick={() => stepZoom(-1)}
          >
            <Icon name="minus" />
          </button>
          <span className="or-stepper__value" aria-live="polite">
            {Math.round(zoom * 100)}%
          </span>
          <button
            type="button"
            className="or-btn or-btn--ghost or-btn--icon"
            aria-label="Zoom in"
            title="Zoom in"
            disabled={zoom >= ZOOM_MAX}
            onClick={() => stepZoom(1)}
          >
            <Icon name="plus" />
          </button>
        </div>
        <button
          type="button"
          className={`or-btn or-btn--ghost or-btn--icon${zoomMode === "fit" ? " is-active" : ""}`}
          aria-label="Fit width"
          title="Fit width"
          aria-pressed={zoomMode === "fit"}
          onClick={() => setZoomMode("fit")}
        >
          <Icon name="fitWidth" />
        </button>
        <form
          className="or-pagejump"
          onSubmit={(e) => {
            e.preventDefault();
            const n = Number(pageInput);
            if (Number.isFinite(n)) goTo(n);
            else setPageInput(String(page));
          }}
        >
          <input
            className="or-input"
            value={pageInput}
            inputMode="numeric"
            aria-label="Page"
            onChange={(e) => setPageInput(e.target.value.replace(/\D/g, ""))}
            onBlur={() => setPageInput(String(page))}
          />
          <span>/ {total || "–"}</span>
        </form>
        <div className="or-vr" />
        <button
          type="button"
          className={`or-btn or-btn--ghost or-btn--icon${chatOpen ? " is-active" : ""}`}
          aria-label={chatOpen ? "Hide chat" : "Show chat"}
          title={chatOpen ? "Hide chat" : "Show chat"}
          aria-pressed={chatOpen}
          onClick={() => setChatOpen(!chatOpen)}
        >
          <Icon name="chat" />
        </button>
      </div>

      <div className="app-reader__body">
        {thumbsOpen && doc && sizes.length > 0 && (
          <Thumbnails doc={doc} sizes={sizes} current={page} onSelect={goTo} />
        )}
        <div className="app-reader__pages">
          {focus && shown && (
            <div className="app-sourcebar" role="region" aria-label="Sources">
              <div className="app-sourcebar__what">
                <span className="app-sourcebar__label">Sources</span>
                <span className="app-sourcebar__question" title={focus.question}>
                  {focus.question}
                </span>
              </div>
              <div className="app-sourcebar__nav">
                <button
                  type="button"
                  className="or-btn or-btn--ghost or-btn--icon"
                  aria-label="Previous source"
                  title="Previous source"
                  onClick={() => stepSource(-1)}
                >
                  <Icon name="chevronUp" />
                </button>
                <span className="or-cap app-sourcebar__count" aria-live="polite">
                  {shown.n} of {focus.sources.length} · {pagesLabel(shown)} · {Math.round(Math.max(0, shown.similarity) * 100)}%
                </span>
                <button
                  type="button"
                  className="or-btn or-btn--ghost or-btn--icon"
                  aria-label="Next source"
                  title="Next source"
                  onClick={() => stepSource(1)}
                >
                  <Icon name="chevronDown" />
                </button>
              </div>
              <label className="app-sourcebar__only">
                <input type="checkbox" checked={onlySources} onChange={(e) => setOnlySources(e.target.checked)} />
                Only source pages
              </label>
              <button
                type="button"
                className="or-btn or-btn--ghost or-btn--icon"
                aria-label="Close sources"
                title="Close sources"
                onClick={() => {
                  setFocus(null);
                  setOnlySources(false);
                }}
              >
                <Icon name="close" />
              </button>
            </div>
          )}
          {doc && sizes.length > 0 ? (
            <PdfPages
              ref={pages}
              doc={doc}
              sizes={sizes}
              zoom={zoom}
              onPageChange={onPageChange}
              onResize={computeFit}
              only={sourcePages}
              marks={marks}
              onMarkClick={(n) => focus && setFocus({ ...focus, n })}
            />
          ) : (
            <div className="app-empty">
              <p className="or-cap">Opening…</p>
            </div>
          )}
        </div>
        {chatOpen && book && (
          <aside className="app-reader__chat" style={{ width: chatWidth }}>
            <div
              className="app-resizer"
              role="separator"
              aria-orientation="vertical"
              aria-label="Resize chat"
              aria-valuemin={CHAT_MIN}
              aria-valuemax={CHAT_MAX}
              aria-valuenow={chatWidth}
              tabIndex={0}
              onPointerDown={startResize}
              onKeyDown={(e) => {
                if (e.key === "ArrowLeft") setChatWidth(Math.min(CHAT_MAX, chatWidth + 20));
                if (e.key === "ArrowRight") setChatWidth(Math.max(CHAT_MIN, chatWidth - 20));
              }}
            />
            <ChatPanel book={book} focus={focus} onOpenSource={setFocus} />
          </aside>
        )}
      </div>

      <div className="app-statusbar or-cap">{total ? `Page ${page} / ${total}` : ""}</div>
    </div>
  );
}
