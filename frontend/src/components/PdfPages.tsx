import type { PDFDocumentProxy, RenderTask } from "pdfjs-dist";
import { forwardRef, useCallback, useEffect, useImperativeHandle, useLayoutEffect, useMemo, useRef, useState } from "react";

/** CSS px per PDF point at 100% zoom */
export const PT_TO_PX = 96 / 72;
const GAP = 24; // space-6 between pages and around them

export interface PageSize {
  w: number;
  h: number;
}

/** Page sizes at scale 1, first page immediately and the rest in the background. */
export function usePageSizes(doc: PDFDocumentProxy | null): PageSize[] {
  const [sizes, setSizes] = useState<PageSize[]>([]);
  useEffect(() => {
    if (!doc) return;
    let cancelled = false;
    (async () => {
      const first = (await doc.getPage(1)).getViewport({ scale: 1 });
      const all: PageSize[] = Array.from({ length: doc.numPages }, () => ({ w: first.width, h: first.height }));
      if (!cancelled) setSizes([...all]);
      for (let i = 2; i <= doc.numPages && !cancelled; i++) {
        const v = (await doc.getPage(i)).getViewport({ scale: 1 });
        if (v.width !== first.width || v.height !== first.height) {
          all[i - 1] = { w: v.width, h: v.height };
          if (i % 50 === 0 || i === doc.numPages) setSizes([...all]);
        }
      }
      if (!cancelled) setSizes([...all]);
    })();
    return () => {
      cancelled = true;
    };
  }, [doc]);
  return sizes;
}

/** Renders one page into a canvas while `visible`; drops the canvas when it isn't. */
export function PageCanvas({
  doc,
  page,
  scale,
  visible,
  className,
}: {
  doc: PDFDocumentProxy;
  page: number;
  scale: number;
  visible: boolean;
  className?: string;
}) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const [drawn, setDrawn] = useState(false);

  useEffect(() => {
    if (!visible) {
      setDrawn(false);
      return;
    }
    let task: RenderTask | null = null;
    let cancelled = false;
    (async () => {
      const p = await doc.getPage(page);
      if (cancelled || !canvas.current) return;
      const dpr = window.devicePixelRatio || 1;
      const viewport = p.getViewport({ scale: scale * dpr });
      const c = canvas.current;
      // render offscreen, then swap, so the old image stays during re-renders (zoom)
      const off = document.createElement("canvas");
      off.width = Math.floor(viewport.width);
      off.height = Math.floor(viewport.height);
      const ctx = off.getContext("2d");
      if (!ctx) return;
      task = p.render({ canvasContext: ctx, viewport });
      try {
        await task.promise;
      } catch {
        return; // cancelled
      }
      if (cancelled) return;
      c.width = off.width;
      c.height = off.height;
      c.getContext("2d")?.drawImage(off, 0, 0);
      setDrawn(true);
    })();
    return () => {
      cancelled = true;
      task?.cancel();
    };
  }, [doc, page, scale, visible]);

  return <canvas ref={canvas} className={className} style={{ opacity: drawn ? 1 : 0 }} aria-hidden="true" />;
}

/** A source's line boxes on one page (fractions of the page), drawn over the canvas. */
export interface PageMark {
  page: number;
  /** source number, shown on its first box */
  n: number;
  rects: [number, number, number, number][];
  active: boolean;
}

export interface PdfPagesHandle {
  /** scroll so `page` is at the top, or so the spot `y` (0–1 down the page) is near the anchor line */
  scrollToPage: (page: number, y?: number) => void;
  /** width available to a page, for fit-width zoom */
  availableWidth: () => number;
}

export const PdfPages = forwardRef<
  PdfPagesHandle,
  {
    doc: PDFDocumentProxy;
    sizes: PageSize[];
    zoom: number;
    onPageChange: (page: number) => void;
    onResize?: () => void;
    /** show only these pages, in this order (all pages when absent) */
    only?: number[] | null;
    marks?: PageMark[];
    onMarkClick?: (n: number) => void;
  }
>(function PdfPages({ doc, sizes, zoom, onPageChange, onResize, only, marks, onMarkClick }, ref) {
  const scroller = useRef<HTMLDivElement>(null);
  const [visible, setVisible] = useState<Set<number>>(new Set([1]));
  const scale = zoom * PT_TO_PX;
  const current = useRef(1);

  // the pages laid out, in order; positions below are indexes into this list
  const order = useMemo(
    () => (only?.length ? only.filter((p) => p >= 1 && p <= sizes.length) : sizes.map((_, i) => i + 1)),
    [only, sizes],
  );

  // top offset of every laid-out page at the current scale
  const offsets = useMemo(() => {
    const out: number[] = [];
    let y = GAP;
    for (const p of order) {
      out.push(y);
      y += Math.floor(sizes[p - 1].h * scale) + GAP;
    }
    out.push(y);
    return out;
  }, [order, sizes, scale]);

  const indexAt = useCallback(
    (y: number) => {
      let lo = 0;
      let hi = order.length - 1;
      while (lo < hi) {
        const mid = (lo + hi + 1) >> 1;
        if (offsets[mid] <= y) lo = mid;
        else hi = mid - 1;
      }
      return lo;
    },
    [offsets, order.length],
  );

  const update = useCallback(() => {
    const el = scroller.current;
    if (!el || !order.length) return;
    const top = el.scrollTop;
    const bottom = top + el.clientHeight;
    // current page: the one under a line 30% down the viewport
    const line = top + el.clientHeight * 0.3;
    const i = indexAt(line);
    const page = order[i];
    if (lastScale.current === scale) {
      const h = Math.floor(sizes[page - 1].h * scale) || 1;
      anchor.current = { page, frac: Math.min(1, Math.max(0, (line - offsets[i]) / h)) };
    }
    if (page !== current.current) {
      current.current = page;
      onPageChange(page);
    }
    // render the visible pages plus one screen above and below
    const first = indexAt(Math.max(0, top - el.clientHeight));
    const last = indexAt(bottom + el.clientHeight);
    setVisible((prev) => {
      const next = new Set(order.slice(first, last + 1));
      if (prev.size === next.size && [...next].every((p) => prev.has(p))) return prev;
      return next;
    });
  }, [indexAt, order, sizes, offsets, scale, onPageChange]);

  useEffect(update, [update]);

  // keep the same spot of the current page under the anchor line when the zoom changes
  const anchor = useRef<{ page: number; frac: number } | null>(null);
  const lastScale = useRef(scale);
  useLayoutEffect(() => {
    const el = scroller.current;
    if (!el || lastScale.current === scale || !anchor.current) return;
    lastScale.current = scale;
    const { page, frac } = anchor.current;
    const i = order.indexOf(page);
    if (i < 0) return;
    const h = Math.floor(sizes[page - 1].h * scale);
    el.scrollTop = offsets[i] + frac * h - el.clientHeight * 0.3;
  }, [scale, offsets, sizes, order]);

  useEffect(() => {
    const el = scroller.current;
    if (!el || !onResize) return;
    const ro = new ResizeObserver(() => onResize());
    ro.observe(el);
    return () => ro.disconnect();
  }, [onResize]);

  useImperativeHandle(
    ref,
    () => ({
      scrollToPage: (page: number, y?: number) => {
        const el = scroller.current;
        if (!el || !order.length) return;
        // a page that isn't laid out: the next one that is (or the last)
        let i = order.findIndex((p) => p >= page);
        if (i < 0) i = order.length - 1;
        if (y === undefined || order[i] !== page) {
          el.scrollTop = offsets[i] - GAP / 2;
        } else {
          el.scrollTop = offsets[i] + y * Math.floor(sizes[page - 1].h * scale) - el.clientHeight * 0.3;
        }
      },
      availableWidth: () => (scroller.current?.clientWidth ?? 800) - GAP * 2,
    }),
    [offsets, order, sizes, scale],
  );

  const marksByPage = useMemo(() => {
    const out = new Map<number, PageMark[]>();
    for (const m of marks ?? []) {
      if (!out.has(m.page)) out.set(m.page, []);
      out.get(m.page)!.push(m);
    }
    // the active source on top
    for (const list of out.values()) list.sort((a, b) => Number(a.active) - Number(b.active));
    return out;
  }, [marks]);

  const width = Math.max(...order.map((p) => Math.floor(sizes[p - 1].w * scale)), 0);

  return (
    <div ref={scroller} className="app-pages" onScroll={update} tabIndex={-1}>
      <div className="app-pages__inner" style={{ height: offsets[offsets.length - 1] ?? 0, minWidth: width + GAP * 2 }}>
        {order.map((page, i) => {
          const s = sizes[page - 1];
          const show = visible.has(page);
          return (
            <div
              key={page}
              className="app-page"
              data-page={page}
              style={{ top: offsets[i], width: Math.floor(s.w * scale), height: Math.floor(s.h * scale) }}
              aria-label={`Page ${page}`}
            >
              {show && <PageCanvas doc={doc} page={page} scale={scale} visible={show} className="app-page__canvas" />}
              {show &&
                marksByPage.get(page)?.map((m) => (
                  <div key={m.n} className={`app-mark${m.active ? " is-active" : ""}`}>
                    {m.rects.map(([x0, y0, x1, y1], j) => (
                      <button
                        key={j}
                        type="button"
                        tabIndex={-1}
                        className="app-mark__box"
                        title={`Source ${m.n}`}
                        style={{ left: `${x0 * 100}%`, top: `${y0 * 100}%`, width: `${(x1 - x0) * 100}%`, height: `${(y1 - y0) * 100}%` }}
                        onClick={() => onMarkClick?.(m.n)}
                      />
                    ))}
                    <span className="app-mark__n" style={{ top: `${m.rects[0][1] * 100}%` }} aria-hidden="true">
                      {m.n}
                    </span>
                  </div>
                ))}
            </div>
          );
        })}
      </div>
    </div>
  );
});
