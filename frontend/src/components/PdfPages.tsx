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

export interface PdfPagesHandle {
  scrollToPage: (page: number) => void;
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
  }
>(function PdfPages({ doc, sizes, zoom, onPageChange, onResize }, ref) {
  const scroller = useRef<HTMLDivElement>(null);
  const [visible, setVisible] = useState<Set<number>>(new Set([1]));
  const scale = zoom * PT_TO_PX;
  const current = useRef(1);

  // top offset of every page at the current scale
  const offsets = useMemo(() => {
    const out: number[] = [];
    let y = GAP;
    for (const s of sizes) {
      out.push(y);
      y += Math.floor(s.h * scale) + GAP;
    }
    out.push(y);
    return out;
  }, [sizes, scale]);

  const pageAt = useCallback(
    (y: number) => {
      let lo = 0;
      let hi = sizes.length - 1;
      while (lo < hi) {
        const mid = (lo + hi + 1) >> 1;
        if (offsets[mid] <= y) lo = mid;
        else hi = mid - 1;
      }
      return lo + 1;
    },
    [offsets, sizes.length],
  );

  const update = useCallback(() => {
    const el = scroller.current;
    if (!el || !sizes.length) return;
    const top = el.scrollTop;
    const bottom = top + el.clientHeight;
    // current page: the one under a line 30% down the viewport
    const line = top + el.clientHeight * 0.3;
    const page = pageAt(line);
    if (lastScale.current === scale) {
      const h = Math.floor(sizes[page - 1].h * scale) || 1;
      anchor.current = { page, frac: Math.min(1, Math.max(0, (line - offsets[page - 1]) / h)) };
    }
    if (page !== current.current) {
      current.current = page;
      onPageChange(page);
    }
    // render the visible pages plus one screen above and below
    const first = pageAt(Math.max(0, top - el.clientHeight));
    const last = pageAt(bottom + el.clientHeight);
    setVisible((prev) => {
      if (prev.size === last - first + 1 && prev.has(first) && prev.has(last)) return prev;
      const next = new Set<number>();
      for (let p = first; p <= last; p++) next.add(p);
      return next;
    });
  }, [pageAt, sizes, offsets, scale, onPageChange]);

  useEffect(update, [update]);

  // keep the same spot of the current page under the anchor line when the zoom changes
  const anchor = useRef<{ page: number; frac: number } | null>(null);
  const lastScale = useRef(scale);
  useLayoutEffect(() => {
    const el = scroller.current;
    if (!el || lastScale.current === scale || !anchor.current) return;
    lastScale.current = scale;
    const { page, frac } = anchor.current;
    const h = Math.floor(sizes[page - 1].h * scale);
    el.scrollTop = offsets[page - 1] + frac * h - el.clientHeight * 0.3;
  }, [scale, offsets, sizes]);

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
      scrollToPage: (page: number) => {
        const el = scroller.current;
        const p = Math.min(Math.max(1, page), sizes.length);
        if (el && offsets[p - 1] !== undefined) el.scrollTop = offsets[p - 1] - GAP / 2;
      },
      availableWidth: () => (scroller.current?.clientWidth ?? 800) - GAP * 2,
    }),
    [offsets, sizes.length],
  );

  const width = Math.max(...sizes.map((s) => Math.floor(s.w * scale)), 0);

  return (
    <div ref={scroller} className="app-pages" onScroll={update} tabIndex={-1}>
      <div className="app-pages__inner" style={{ height: offsets[offsets.length - 1] ?? 0, minWidth: width + GAP * 2 }}>
        {sizes.map((s, i) => {
          const page = i + 1;
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
            </div>
          );
        })}
      </div>
    </div>
  );
});
